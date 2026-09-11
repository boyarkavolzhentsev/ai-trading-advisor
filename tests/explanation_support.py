"""Shared fixtures for LLM Explanation Layer tests.

Builds real ``RuntimeCycleResult`` objects via the real ``run_runtime_cycle``
(reusing the same support modules ``tests/test_runtime_cycle.py`` itself
uses) for every scenario the explanation layer must handle - never a
hand-rolled ``RuntimeCycleResult``. Also provides ``FakeExplanationLLMClient``,
a scriptable fake satisfying ``ExplanationLLMClient`` without any real LLM
SDK.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.market import MarketType
from app.core.enums.mt5_history import MT5DealEntry
from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.enums.order import OrderSide
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.explanation import ExplanationLLMResponse, ExplanationRequest
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.core.models.runtime_cycle import RuntimeCycleResult
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
from tests.mt5_matching_support import SIGNAL_TIME, VALID_UNTIL, default_candidate_deal, default_position_record, default_tracked_recommendation
from tests.risk_gate_support import default_config
from tests.runtime_cycle_support import RuntimeCycleFakeClient, default_account_facts

__all__ = [
    "TARGET_SYMBOL",
    "FakeExplanationLLMClient",
    "blocked_result",
    "degraded_issuance_suppressed_result",
    "degraded_with_recommendation_present_result",
    "make_stores",
    "netting_existing_broker_position_blocked_result",
    "netting_existing_unresolved_blocked_result",
    "netting_flat_allowed_result",
    "netting_multiple_actionable_blocked_result",
    "provenance_persistence_failure_result",
    "ready_actionable_hedging_result",
    "ready_actionable_hedging_result_with_currency",
    "ready_multiple_actionable_hedging_result",
    "ready_no_actionable_result",
    "tracking_lifecycle_result",
    "tracking_persistence_failure_result",
    "unknown_mode_multiple_actionable_blocked_result",
    "unknown_mode_result",
]

ROLLOVER_POLICY = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0)
TARGET_SYMBOL = "BTCUSDT"


def make_stores(tmp_path: Path):
    tracking_dir = tmp_path / "tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    rollover_persistence = MT5RolloverStatePersistence(tmp_path / "rollover.json")
    tracking_persistence = MT5RecommendationPersistence(tracking_dir)
    provenance_persistence = MT5RecommendationProvenancePersistence(tracking_dir)
    return rollover_persistence, tracking_persistence, provenance_persistence


def _actionable_client(**overrides: object) -> RuntimeCycleFakeClient:
    fields: dict[str, object] = dict(
        account_facts=default_account_facts(),
        positions_result=("OK", ()),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts()},
        history_deals_result=("OK", ()),
    )
    fields.update(overrides)
    return RuntimeCycleFakeClient(**fields)


def _run(tmp_path: Path, client: RuntimeCycleFakeClient, stores=None, **overrides) -> RuntimeCycleResult:
    rollover_persistence, tracking_persistence, provenance_persistence = stores or make_stores(tmp_path)
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
    return run_runtime_cycle(**kwargs)


def ready_actionable_hedging_result(tmp_path: Path) -> RuntimeCycleResult:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.HEDGING))
    return _run(tmp_path, client)


def ready_actionable_hedging_result_with_currency(tmp_path: Path, currency: str) -> RuntimeCycleResult:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.HEDGING, currency=currency))
    return _run(tmp_path, client)


def ready_multiple_actionable_hedging_result(tmp_path: Path) -> RuntimeCycleResult:
    # narrower bid/ask spread (0.02 vs the default 0.10) so the real,
    # bid/ask-based broker-minimum-stop check can pass for BOTH directions
    # simultaneously from one shared Binance reference (see
    # tests/final_recommendation_support.py::run_pipeline's own docstring).
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.HEDGING),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts(bid=Decimal("100.08"))},
    )
    return _run(
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


def ready_no_actionable_result(tmp_path: Path) -> RuntimeCycleResult:
    client = _actionable_client()
    return _run(tmp_path, client, technical=None, m15_market_structure=None, trade_ids={})


def blocked_result(tmp_path: Path) -> RuntimeCycleResult:
    client = RuntimeCycleFakeClient(runtime_status=MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.INITIALIZATION_FAILED))
    return _run(tmp_path, client)


def degraded_with_recommendation_present_result(tmp_path: Path) -> RuntimeCycleResult:
    """PARTIAL_DEGRADED (one corrupt unrelated tracked recommendation
    excluded) while a fresh recommendation is still issued this cycle."""
    stores = make_stores(tmp_path)
    (tmp_path / "tracking" / "bad.json").write_text("{not valid json", encoding="utf-8")
    client = _actionable_client()
    return _run(tmp_path, client, stores=stores)


def degraded_issuance_suppressed_result(tmp_path: Path) -> RuntimeCycleResult:
    """PARTIAL_DEGRADED with positions unavailable - issuance suppressed,
    existing tracking still advances."""
    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))
    client = _actionable_client(positions_result=("UNAVAILABLE", ()), history_deals_result=("OK", (default_candidate_deal(),)))
    return _run(tmp_path, client, stores=stores)


def netting_flat_allowed_result(tmp_path: Path) -> RuntimeCycleResult:
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING))
    return _run(tmp_path, client)


def netting_existing_broker_position_blocked_result(tmp_path: Path) -> RuntimeCycleResult:
    existing_position = MT5Position(
        as_of=NOW, ticket=555, symbol=TARGET_SYMBOL, side=OrderSide.BUY, volume=Decimal("1"), price_open=Decimal("100"), price_current=Decimal("100")
    )
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING), positions_result=("OK", (existing_position,))
    )
    return _run(tmp_path, client)


def netting_existing_unresolved_blocked_result(tmp_path: Path) -> RuntimeCycleResult:
    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    tracking_persistence.write(
        "existing-t1", default_tracked_recommendation(position_record=default_position_record(trade_id="existing-t1", symbol=TARGET_SYMBOL))
    )
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING))
    return _run(tmp_path, client, stores=stores)


def netting_multiple_actionable_blocked_result(tmp_path: Path) -> RuntimeCycleResult:
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.NETTING),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts(bid=Decimal("100.08"))},
    )
    return _run(
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


def unknown_mode_result(tmp_path: Path) -> RuntimeCycleResult:
    """UNKNOWN + flat/uncontested/single-actionable - the safe-invariant
    branch: the guard genuinely resolves to ALLOWED."""
    client = _actionable_client(account_facts=default_account_facts(margin_mode=AccountPositionMode.UNKNOWN))
    return _run(tmp_path, client)


def unknown_mode_multiple_actionable_blocked_result(tmp_path: Path) -> RuntimeCycleResult:
    """UNKNOWN + multiple actionable FinalRecommendations - the unsafe-
    condition branch: identical scenario to
    ``netting_multiple_actionable_blocked_result`` except the account
    position mode is genuinely ``UNKNOWN`` rather than ``NETTING``, so the
    guard's ``BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS`` outcome is reached
    under UNKNOWN's own conservative fail-closed handling, never HEDGING's."""
    client = _actionable_client(
        account_facts=default_account_facts(margin_mode=AccountPositionMode.UNKNOWN),
        symbol_facts_by_symbol={TARGET_SYMBOL: symbol_facts(bid=Decimal("100.08"))},
    )
    return _run(
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


def tracking_persistence_failure_result(tmp_path: Path, monkeypatch) -> RuntimeCycleResult:
    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    monkeypatch.setattr(tracking_persistence, "write", lambda *_a, **_k: False)
    client = _actionable_client()
    return _run(tmp_path, client, stores=stores)


def provenance_persistence_failure_result(tmp_path: Path, monkeypatch) -> RuntimeCycleResult:
    stores = make_stores(tmp_path)
    _, _, provenance_persistence = stores
    monkeypatch.setattr(provenance_persistence, "write", lambda *_a, **_k: False)
    client = _actionable_client()
    return _run(tmp_path, client, stores=stores)


def tracking_lifecycle_result(tmp_path: Path, status: str) -> RuntimeCycleResult:
    """Yields a ``RuntimeCycleResult`` whose ``advanced_tracking`` contains
    exactly one existing tracked recommendation that reaches ``status``
    (``"PENDING"``, ``"OPEN"``, ``"WIN"``, ``"LOSS"``, ``"BREAKEVEN"``, or
    ``"NOT_FILLED"``) - built purely from real Stage 10E deal fixtures, never
    a hand-rolled ``PositionRecord`` status."""
    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    as_of = NOW
    history_deals_result: tuple[str, tuple] = ("OK", ())

    if status == "PENDING":
        as_of = SIGNAL_TIME + timedelta(minutes=1)
        history_deals_result = ("OK", ())
    elif status == "OPEN":
        as_of = SIGNAL_TIME + timedelta(minutes=1)
        history_deals_result = ("OK", (default_candidate_deal(),))
    elif status == "NOT_FILLED":
        as_of = VALID_UNTIL + timedelta(minutes=1)
        history_deals_result = ("OK", ())
    elif status in ("WIN", "LOSS", "BREAKEVEN"):
        profit = {"WIN": Decimal("50"), "LOSS": Decimal("-50"), "BREAKEVEN": Decimal("0")}[status]
        entry = default_candidate_deal(ticket=1, commission=Decimal("0"))
        exit_deal = default_candidate_deal(
            ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=3), profit=profit, commission=Decimal("0")
        )
        as_of = SIGNAL_TIME + timedelta(minutes=4)
        history_deals_result = ("OK", (entry, exit_deal))
    else:
        raise ValueError(f"unsupported status for fixture: {status}")

    client = _actionable_client(history_deals_result=history_deals_result)
    return _run(tmp_path, client, stores=stores, as_of=as_of, technical=None, m15_market_structure=None, trade_ids={})


class FakeExplanationLLMClient:
    """Scriptable fake satisfying ``ExplanationLLMClient``. Each entry in
    ``responses`` is either an ``ExplanationLLMResponse`` to return or an
    ``Exception`` instance to raise, consumed in order, one per ``explain``
    call."""

    def __init__(self, responses: list[ExplanationLLMResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[ExplanationRequest] = []

    def explain(self, request: ExplanationRequest) -> ExplanationLLMResponse:
        self.calls.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
