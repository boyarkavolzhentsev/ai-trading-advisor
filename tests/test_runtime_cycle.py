"""Part F Runtime Cycle Orchestration - end-to-end coordinator tests (Final
Runtime Integration, Part F).

Builds real upstream Stage 1-4/Decision-Risk-Pipeline/Final-Recommendation
fixtures via the same real support modules ``tests/test_final_recommendation.py``
itself uses, then drives the whole cycle through the real
``run_runtime_cycle`` with a controllable fake ``MT5ClientProtocol`` - never a
hand-rolled ``RuntimeCycleResult``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.final_recommendation import FinalRecommendationOutcome
from app.core.enums.market import MarketType
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_rollover import MT5RolloverOutcome
from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.enums.order import OrderSide
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeStatus
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.mt5.persistence import MT5RolloverStatePersistence
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.recommendation_provenance_persistence import MT5RecommendationProvenancePersistence
from app.orchestration.runtime_cycle import run_runtime_cycle
from tests.final_recommendation_support import (
    NOW,
    actionable_trend_market_structure,
    context,
    opposite_direction_market_structure,
    opposite_direction_technical,
    symbol_facts,
    trend_following_technical,
)
from tests.market_evaluation_support import full_flow_result
from tests.mt5_matching_support import default_candidate_deal, default_position_record, default_tracked_recommendation
from tests.risk_gate_support import default_config
from tests.runtime_cycle_support import RuntimeCycleFakeClient, default_account_facts

ROLLOVER_POLICY = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0)
TARGET_SYMBOL = "BTCUSDT"


def _make_stores(tmp_path: Path):
    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    rollover_persistence = MT5RolloverStatePersistence(tmp_path / "rollover.json")
    tracking_persistence = MT5RecommendationPersistence(tracking_dir)
    provenance_persistence = MT5RecommendationProvenancePersistence(tracking_dir)
    return rollover_persistence, tracking_persistence, provenance_persistence


def _run_cycle(tmp_path: Path, client: RuntimeCycleFakeClient, stores=None, **overrides):
    rollover_persistence, tracking_persistence, provenance_persistence = stores or _make_stores(tmp_path)
    kwargs = dict(
        client=client,
        as_of=NOW,
        rollover_policy=ROLLOVER_POLICY,
        rollover_persistence=rollover_persistence,
        tracking_persistence=tracking_persistence,
        provenance_persistence=provenance_persistence,
        trading_cycle_config=default_config(),
        market=MarketType.CRYPTO,
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        context=context(),
        mt5_symbol=TARGET_SYMBOL,
        binance_reference_price=Decimal("100.10"),
        max_price_basis_divergence_percent=Decimal("100"),
        technical=trend_following_technical(),
        m15_market_structure=actionable_trend_market_structure(),
    )
    kwargs.update(overrides)
    result = run_runtime_cycle(**kwargs)
    return result, rollover_persistence, tracking_persistence, provenance_persistence


def _actionable_client(**client_overrides) -> RuntimeCycleFakeClient:
    fields: dict[str, object] = dict(
        account_facts=default_account_facts(),
        positions_result=("OK", ()),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts()},
        history_deals_result=("OK", ()),
    )
    fields.update(client_overrides)
    return RuntimeCycleFakeClient(**fields)


# --- happy path: HEDGING ---


def test_full_happy_path_hedging_issues_and_persists(tmp_path: Path) -> None:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.HEDGING))
    result, _, tracking_persistence, provenance_persistence = _run_cycle(tmp_path, client)

    assert result.mt5_runtime_status.state is MT5ConnectivityState.AVAILABLE
    assert result.positions_read_status == "OK"
    assert result.history_read_status == "OK"
    assert result.rollover_snapshot is not None
    assert result.rollover_snapshot.rollover_outcome is MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY
    assert result.rollover_persisted is True
    assert result.account_risk_snapshot_assembly is not None
    assert result.decision_risk_pipeline_result is not None
    assert result.final_recommendation_construction_result is not None
    assert result.final_recommendation_construction_result.outcome is FinalRecommendationOutcome.SOME_ACTIONABLE
    assert result.netting_guard_result is None  # HEDGING: guard never evaluated
    assert len(result.new_tracking_results) == 1
    creation_result = result.new_tracking_results[0].tracking_creation_result
    assert creation_result.outcome is MT5TrackedRecommendationCreationOutcome.CREATED
    assert len(result.new_tracking_persistence_outcomes) == 1
    assert result.new_tracking_persistence_outcomes[0].tracking_persisted is True
    assert result.new_tracking_persistence_outcomes[0].provenance_persisted is True
    assert result.outcome is RuntimeCycleOutcome.READY

    _, persisted_tracked = tracking_persistence.read("trade-1")
    assert persisted_tracked is not None
    _, persisted_provenance = provenance_persistence.read("trade-1")
    assert persisted_provenance is not None
    assert persisted_provenance.family is StrategyFamily.TREND_FOLLOWING


def test_shutdown_always_called_on_happy_path(tmp_path: Path) -> None:
    client = _actionable_client()
    _run_cycle(tmp_path, client)
    assert client.shutdown_calls == 1


# --- happy path: NETTING, flat and uncontested ---


def test_full_happy_path_netting_allowed_when_flat_and_uncontested(tmp_path: Path) -> None:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING))
    result, *_ = _run_cycle(tmp_path, client)

    assert result.netting_guard_result is not None
    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.ALLOWED
    assert result.netting_guard_result.account_position_mode is AccountPositionMode.NETTING
    assert len(result.new_tracking_results) == 1


def test_multiple_actionable_netting_blocks_all(tmp_path: Path) -> None:
    # narrower bid/ask spread (0.02 vs the default 0.10) so the real,
    # bid/ask-based broker-minimum-stop check can pass for BOTH directions
    # simultaneously from one shared Binance reference (see
    # tests/final_recommendation_support.py::run_pipeline's own docstring).
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts(bid=Decimal("100.08"))},
    )
    result, *_ = _run_cycle(
        tmp_path,
        client,
        technical=opposite_direction_technical(),
        m15_market_structure=opposite_direction_market_structure(),
        flow=full_flow_result(),
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-long", StrategyFamily.BREAKOUT: "trade-short"},
        # a single shared Binance reference strictly between the LONG stop
        # (100) and the SHORT stop (100.10) - both directions translate
        # positively (mirrors the one-shared-reference-per-cycle production
        # reality).
        binance_reference_price=Decimal("100.05"),
    )

    assert result.final_recommendation_construction_result is not None
    actionable_count = sum(
        1
        for r in result.final_recommendation_construction_result.family_results
        if r.recommendation is not None
    )
    assert actionable_count == 2
    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS
    assert result.new_tracking_results == ()
    assert result.new_tracking_persistence_outcomes == ()
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_existing_broker_position_blocks_netting_issuance(tmp_path: Path) -> None:
    existing_position = MT5Position(
        as_of=NOW, ticket=555, symbol=TARGET_SYMBOL, side=OrderSide.BUY, volume=Decimal("1"), price_open=Decimal("100"), price_current=Decimal("100")
    )
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING),
        positions_result=("OK", (existing_position,)),
    )
    result, *_ = _run_cycle(tmp_path, client)

    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION
    assert result.new_tracking_results == ()


def test_existing_pending_tracked_recommendation_blocks_netting_issuance(tmp_path: Path) -> None:
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write(
        "existing-t1", default_tracked_recommendation(position_record=default_position_record(trade_id="existing-t1", symbol=TARGET_SYMBOL))
    )
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING))
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION
    assert result.new_tracking_results == ()


def test_unknown_mode_uses_netting_restrictions(tmp_path: Path) -> None:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.UNKNOWN))
    result, *_ = _run_cycle(tmp_path, client)

    assert result.netting_guard_result is not None
    assert result.netting_guard_result.account_position_mode is AccountPositionMode.UNKNOWN
    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.ALLOWED  # flat + uncontested + single actionable


# --- MT5 connectivity / degraded scenarios ---


def test_mt5_initialize_failure_blocks_cycle(tmp_path: Path) -> None:
    client = RuntimeCycleFakeClient(runtime_status=MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.INITIALIZATION_FAILED))
    result, *_ = _run_cycle(tmp_path, client)

    assert result.outcome is RuntimeCycleOutcome.BLOCKED
    assert result.account_facts is None
    assert result.account_risk_snapshot_assembly is None
    assert result.decision_risk_pipeline_result is None
    assert result.advanced_tracking == ()
    assert client.positions_calls == 0
    assert client.history_deals_calls == []
    assert client.shutdown_calls == 1


def test_account_facts_unavailable_still_advances_existing_tracking(tmp_path: Path) -> None:
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    client = RuntimeCycleFakeClient(
        account_facts=None,
        positions_result=("UNAVAILABLE", ()),
        history_deals_result=("OK", (default_candidate_deal(),)),
    )
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert result.account_facts is None
    assert result.rollover_snapshot is None
    assert result.account_risk_snapshot_assembly is None
    assert result.decision_risk_pipeline_result is None
    assert result.final_recommendation_construction_result is None
    assert len(result.advanced_tracking) == 1
    assert result.advanced_tracking[0].tracked_recommendation.matched_position_id == 7001
    assert result.advanced_tracking[0].persisted is True
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_positions_unavailable_blocks_open_risk_and_assembly_but_not_advancement(tmp_path: Path) -> None:
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    client = _actionable_client(positions_result=("UNAVAILABLE", ()), history_deals_result=("OK", (default_candidate_deal(),)))
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert result.positions_read_status == "UNAVAILABLE"
    assert result.open_risk_assessment is None
    assert result.account_risk_snapshot_assembly is None
    assert result.final_recommendation_construction_result is None
    assert result.new_tracking_results == ()
    # rollover is independent of positions and still computed:
    assert result.rollover_snapshot is not None
    # existing-tracking advancement needs only history, unaffected:
    assert len(result.advanced_tracking) == 1
    assert result.advanced_tracking[0].tracked_recommendation.matched_position_id == 7001
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_positions_unmappable_position_side_behaves_like_unavailable(tmp_path: Path) -> None:
    """Closes a previously-identified coverage gap: ``UNMAPPABLE_POSITION_SIDE``
    exercises the identical ``!= "OK"`` code path as ``UNAVAILABLE``, but the
    exact literal value must still be preserved verbatim on the result -
    never collapsed/renamed, never fabricated into a different status."""
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    client = _actionable_client(positions_result=("UNMAPPABLE_POSITION_SIDE", ()), history_deals_result=("OK", (default_candidate_deal(),)))
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert result.positions_read_status == "UNMAPPABLE_POSITION_SIDE"
    assert result.open_risk_assessment is None
    assert result.account_risk_snapshot_assembly is None
    assert result.decision_risk_pipeline_result is None
    assert result.final_recommendation_construction_result is None
    assert result.new_tracking_results == ()
    # target symbol facts are still attempted regardless of positions status:
    assert result.target_symbol_facts_available is True
    # rollover is independent of positions and still computed:
    assert result.rollover_snapshot is not None
    # existing-tracking advancement needs only history, unaffected - no positions fabricated:
    assert len(result.advanced_tracking) == 1
    assert result.advanced_tracking[0].tracked_recommendation.matched_position_id == 7001
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_history_malformed_timestamp_behaves_like_unavailable(tmp_path: Path) -> None:
    """Closes a previously-identified coverage gap: ``MALFORMED_TIMESTAMP``
    exercises the identical ``!= "OK"`` code path as ``UNAVAILABLE`` for
    Stage 10D, and existing-tracking advancement is threaded the exact
    malformed status unchanged (Stage 10E's own ``advance_tracked_recommendation``
    already handles a non-``"OK"`` history status safely - never fabricated
    to ``"OK"`` here)."""
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    client = _actionable_client(history_deals_result=("MALFORMED_TIMESTAMP", ()))
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert result.history_read_status == "MALFORMED_TIMESTAMP"
    assert result.realized_daily_pnl_assessment is None
    assert result.account_risk_snapshot_assembly is None
    assert result.decision_risk_pipeline_result is None
    assert result.final_recommendation_construction_result is None
    assert result.new_tracking_results == ()
    # rollover and open-risk are independent of history and still computed:
    assert result.rollover_snapshot is not None
    assert result.open_risk_assessment is not None
    # existing-tracking advancement still runs, using the actual malformed status unchanged:
    assert len(result.advanced_tracking) == 1
    advanced = result.advanced_tracking[0].tracked_recommendation
    assert advanced.matched_position_id is None
    assert advanced.position_record.status is TradeStatus.PENDING
    assert result.advanced_tracking[0].persisted is True
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_history_unavailable_blocks_realized_pnl_and_assembly(tmp_path: Path) -> None:
    client = _actionable_client(history_deals_result=("UNAVAILABLE", ()))
    result, *_ = _run_cycle(tmp_path, client)

    assert result.history_read_status == "UNAVAILABLE"
    assert result.realized_daily_pnl_assessment is None
    assert result.account_risk_snapshot_assembly is None
    assert result.final_recommendation_construction_result is None
    # rollover and open-risk are independent of history and still computed:
    assert result.rollover_snapshot is not None
    assert result.open_risk_assessment is not None
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_zero_actionable_recommendations_no_issuance(tmp_path: Path) -> None:
    client = _actionable_client()
    result, *_ = _run_cycle(tmp_path, client, technical=None, m15_market_structure=None, trade_ids={})

    assert result.final_recommendation_construction_result is not None
    assert result.final_recommendation_construction_result.outcome is FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
    assert result.new_tracking_results == ()
    assert result.new_tracking_persistence_outcomes == ()


# --- read-once / dedup ---


def test_positions_and_history_read_exactly_once(tmp_path: Path) -> None:
    client = _actionable_client()
    _run_cycle(tmp_path, client)
    assert client.positions_calls == 1
    assert len(client.history_deals_calls) == 1


def test_symbol_facts_called_at_most_once_per_unique_symbol(tmp_path: Path) -> None:
    other_symbol_position = MT5Position(
        as_of=NOW, ticket=1, symbol="ETHUSDT", side=OrderSide.BUY, volume=Decimal("1"), price_open=Decimal("100"), price_current=Decimal("100"), stop_loss=Decimal("90")
    )
    client = _actionable_client(
        positions_result=("OK", (other_symbol_position,)),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts(), "ETHUSDT": symbol_facts(symbol="ETHUSDT")},
    )
    _run_cycle(tmp_path, client)
    assert client.symbol_facts_calls == sorted(client.symbol_facts_calls)
    assert len(client.symbol_facts_calls) == len(set(client.symbol_facts_calls))
    assert set(client.symbol_facts_calls) == {TARGET_SYMBOL, "ETHUSDT"}


def test_target_symbol_facts_unavailable_is_directly_observable(tmp_path: Path) -> None:
    """The exact Part F pre-commit blocker this test locks in: a caller must
    be able to read ``target_symbol_facts_available`` directly - never infer
    the cause from the unrelated combination of
    ``decision_risk_pipeline_result``/``final_recommendation_construction_result``
    being present/absent."""
    client = _actionable_client(symbol_facts_by_symbol={})
    result, _, tracking_persistence, provenance_persistence = _run_cycle(tmp_path, client)

    # the fact itself, directly - no inference from unrelated None fields:
    assert result.target_symbol_facts_available is False

    assert result.decision_risk_pipeline_result is not None  # Stage 5-9 still ran (symbol_facts is optional there)
    assert result.final_recommendation_construction_result is None
    assert result.new_tracking_results == ()
    assert result.new_tracking_persistence_outcomes == ()
    assert tracking_persistence.list_trade_ids() == ()
    assert provenance_persistence.list_trade_ids() == ()

    # existing partial results remain preserved despite issuance being suppressed:
    assert result.rollover_snapshot is not None
    assert result.open_risk_assessment is not None
    assert result.account_risk_snapshot_assembly is not None

    # target-symbol-facts unavailability must degrade the coarse outcome:
    # issuance could not complete even though other sub-components succeeded.
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED
    assert client.symbol_facts_calls.count(TARGET_SYMBOL) == 1  # no second symbol_facts read


def test_target_symbol_facts_available_true_does_not_itself_degrade_cycle(tmp_path: Path) -> None:
    """A. ``target_symbol_facts_available is True`` must never, by itself,
    push the cycle into PARTIAL_DEGRADED."""
    client = _actionable_client()
    result, *_ = _run_cycle(tmp_path, client)
    assert result.target_symbol_facts_available is True
    assert result.outcome is RuntimeCycleOutcome.READY


def test_healthy_cycle_zero_actionable_remains_ready(tmp_path: Path) -> None:
    """B. "No trade" is not a failure: target symbol facts available, every
    other sub-component healthy, zero actionable recommendations -> READY."""
    client = _actionable_client()
    result, *_ = _run_cycle(tmp_path, client, technical=None, m15_market_structure=None, trade_ids={})
    assert result.target_symbol_facts_available is True
    assert result.final_recommendation_construction_result.outcome is FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
    assert result.outcome is RuntimeCycleOutcome.READY


def test_target_symbol_facts_available_none_when_connectivity_unavailable(tmp_path: Path) -> None:
    """C. Connectivity failure remains BLOCKED, never PARTIAL_DEGRADED - the
    ``None`` (not-attempted) branch must not be independently classified as
    a degradation; ``RuntimeCycleOutcome.BLOCKED`` already owns this path."""
    client = RuntimeCycleFakeClient(runtime_status=MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.INITIALIZATION_FAILED))
    result, *_ = _run_cycle(tmp_path, client)
    assert result.target_symbol_facts_available is None
    assert result.outcome is RuntimeCycleOutcome.BLOCKED


# --- corruption isolation ---


def test_corrupt_tracking_isolated_others_still_advance(tmp_path: Path) -> None:
    rollover_persistence, tracking_persistence, provenance_persistence = _make_stores(tmp_path)
    tracking_persistence.write("good", default_tracked_recommendation(position_record=default_position_record(trade_id="good")))
    (tmp_path / "tracking" / "bad.json").write_text("{not valid json", encoding="utf-8")

    client = _actionable_client(history_deals_result=("OK", (default_candidate_deal(),)))
    result, *_ = _run_cycle(tmp_path, client, stores=(rollover_persistence, tracking_persistence, provenance_persistence))

    assert len(result.excluded_tracked_recommendations) == 1
    assert result.excluded_tracked_recommendations[0].trade_id == "bad"
    assert result.excluded_tracked_recommendations[0].read_status == "CORRUPT"
    assert len(result.advanced_tracking) == 1
    assert result.advanced_tracking[0].trade_id == "good"
    assert result.advanced_tracking[0].tracked_recommendation.matched_position_id == 7001
    assert result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


# --- new recommendation same-cycle advancement policy (documented, §28) ---


def test_new_recommendation_not_advanced_in_same_cycle(tmp_path: Path) -> None:
    """A freshly created recommendation is only ever created and persisted
    as PENDING this cycle - never advanced/matched in the same cycle it was
    issued, even if a qualifying deal already exists in the shared history
    tuple. This avoids a second history read and matches the smallest safe
    behavior confirmed in the approved design."""
    matching_deal = default_candidate_deal(symbol=TARGET_SYMBOL, position_id=8001, time=NOW - timedelta(minutes=1))
    client = _actionable_client(history_deals_result=("OK", (matching_deal,)))
    result, _, tracking_persistence, _ = _run_cycle(tmp_path, client)

    assert len(result.new_tracking_results) == 1
    tracked = result.new_tracking_results[0].tracking_creation_result.tracked_recommendation
    assert tracked is not None
    assert tracked.matched_position_id is None
    assert tracked.position_record.status is TradeStatus.PENDING

    _, persisted = tracking_persistence.read("trade-1")
    assert persisted.matched_position_id is None
    assert persisted.position_record.status is TradeStatus.PENDING


def test_next_cycle_advances_recommendation_created_previous_cycle(tmp_path: Path) -> None:
    stores = _make_stores(tmp_path)
    client_cycle_1 = _actionable_client()
    result_1, *_ = _run_cycle(tmp_path, client_cycle_1, stores=stores)
    approved_volume = result_1.new_tracking_results[0].tracking_creation_result.tracked_recommendation.approved_broker_volume

    matching_deal = default_candidate_deal(symbol=TARGET_SYMBOL, position_id=8001, time=NOW + timedelta(minutes=1), volume=approved_volume)
    client_cycle_2 = _actionable_client(history_deals_result=("OK", (matching_deal,)))
    result_2, *_ = _run_cycle(
        tmp_path, client_cycle_2, stores=stores, as_of=NOW + timedelta(minutes=5), technical=None, m15_market_structure=None, trade_ids={}
    )

    advanced = next(entry for entry in result_2.advanced_tracking if entry.trade_id == "trade-1")
    assert advanced.tracked_recommendation.matched_position_id == 8001
    assert advanced.tracked_recommendation.position_record.status is TradeStatus.OPEN


# --- explicit MarketType / trade_ids passthrough ---


def test_market_type_explicit_passthrough(tmp_path: Path) -> None:
    client = _actionable_client()
    result, *_ = _run_cycle(tmp_path, client, market=MarketType.FX)
    tracked = result.new_tracking_results[0].tracking_creation_result.tracked_recommendation
    assert tracked.position_record.market is MarketType.FX


def test_explicit_trade_id_preserved_no_generation(tmp_path: Path) -> None:
    client = _actionable_client()
    result, *_ = _run_cycle(tmp_path, client, trade_ids={StrategyFamily.TREND_FOLLOWING: "operator-supplied-77"})
    assert result.new_tracking_results[0].trade_id == "operator-supplied-77"


# --- provider-specific symbol routing (corrective design closure,
# "PROVIDER SYMBOL SPLIT + PRICE-BASIS RECONCILIATION") --------------------


def test_mt5_symbol_and_binance_context_symbol_route_to_distinct_facts(tmp_path: Path) -> None:
    """End-to-end proof, with genuinely distinct strings (never the same
    string doing double duty): MT5 symbol_facts/netting-guard/tracking all
    use the MT5 broker symbol (BTCUSDt); the Binance analytical identity
    embedded in context (BTCUSDT) is never used for any of those, and never
    reaches MT5Client.symbol_facts()."""
    mt5_symbol = "BTCUSDt"
    binance_symbol = "BTCUSDT"
    client = _actionable_client(symbol_facts_by_symbol={mt5_symbol: symbol_facts(symbol=mt5_symbol)})

    result, _, tracking_persistence, _ = _run_cycle(
        tmp_path,
        client,
        context=context(symbol=binance_symbol),
        mt5_symbol=mt5_symbol,
    )

    # MT5 symbol_facts() was called with the MT5 symbol only:
    assert client.symbol_facts_calls == [mt5_symbol]
    assert binance_symbol not in client.symbol_facts_calls

    # target-symbol-facts resolution succeeded against the MT5 symbol:
    assert result.target_symbol_facts_available is True

    # the issued recommendation/tracked position carry the MT5 symbol, never the Binance one:
    assert len(result.new_tracking_results) == 1
    tracked = result.new_tracking_results[0].tracking_creation_result.tracked_recommendation
    assert tracked.position_record.symbol == mt5_symbol
    assert tracked.position_record.symbol != binance_symbol

    _, persisted = tracking_persistence.read("trade-1")
    assert persisted.position_record.symbol == mt5_symbol


def test_netting_guard_compares_mt5_symbol_against_mt5_position_symbol(tmp_path: Path) -> None:
    """The netting guard's broker-position check must compare the MT5
    symbol against real MT5Position.symbol values - never the Binance
    analytical symbol, which a real broker position can never report."""
    mt5_symbol = "BTCUSDt"
    binance_symbol = "BTCUSDT"
    existing_position = MT5Position(
        as_of=NOW, ticket=555, symbol=mt5_symbol, side=OrderSide.BUY, volume=Decimal("1"), price_open=Decimal("100"), price_current=Decimal("100")
    )
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING),
        positions_result=("OK", (existing_position,)),
        symbol_facts_by_symbol={mt5_symbol: symbol_facts(symbol=mt5_symbol)},
    )

    result, *_ = _run_cycle(tmp_path, client, context=context(symbol=binance_symbol), mt5_symbol=mt5_symbol)

    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION
    assert result.netting_guard_result.symbol == mt5_symbol
