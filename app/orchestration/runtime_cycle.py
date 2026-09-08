"""Deterministic Runtime Cycle Orchestration (Final Runtime Integration,
Part F).

The first intentionally impure runtime-cycle boundary in this repository.
``run_runtime_cycle`` is the one narrow coordinator that owns every MT5 read
(``MT5ClientProtocol``), every persistence read/write, and the deterministic
sequencing that threads one caller-supplied cycle ``as_of`` and one
read-once/thread-many confirmed positions/history snapshot through the
already-existing, unmodified pure stages:

    Stage 10B rollover -> Stage 10C open risk -> Stage 10D realized daily PnL
    -> Runtime Fact Assembly -> Decision/Risk Pipeline -> Final Recommendation
    -> Part F NETTING/UNKNOWN issuance guard -> Part E tracking creation
    -> Stage 10E existing-tracking advancement -> explicit persistence

Never reimplements any financial/matching/risk/PnL formula: every such
computation remains the exclusive authority of its existing owner
(``app.mt5.rollover``/``app.mt5.risk``/``app.mt5.history``/``app.mt5.tracker``/
``app.mt5.matching``/``app.orchestration.facts``/``app.orchestration.
decision_risk_pipeline``/``app.orchestration.final_recommendation``/
``app.orchestration.tracking_integration``). Never invokes
``RiskGate``/``PortfolioSupervisor``/``SessionGate`` independently - Stage
7/8/9 run only inside ``evaluate_decision_risk_pipeline`` itself. Never
places, checks, modifies, or cancels an order of any kind - MT5 remains
read/tracking only.

``assess_open_risk``/``compute_realized_daily_pnl`` are each called only once
their own underlying MT5 read (``positions()``/``history_deals()``) is
confirmed ``"OK"``: neither ``MT5OpenRiskBlockReason`` nor
``MT5RealizedPnLBlockReason`` defines a "the read itself failed" member, so
fabricating a call with an empty/substitute tuple would silently misreport a
genuinely unknown broker state as a confirmed one. When any of the three
Stage 10B/10C/10D sub-assessments could not be legitimately computed,
``AccountRiskSnapshotAssembly``/``DecisionRiskPipelineResult``/
``FinalRecommendationConstructionResult`` are simply never constructed this
cycle (remaining ``None`` on ``RuntimeCycleResult``) - never forced through
via an invented block reason.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.config.trading_cycle import TradingCycleConfig
from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.market import MarketType
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeStatus
from app.core.models.base import Symbol, Timestamp
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.high_impact_event import HighImpactEventContext, HighImpactEventSymbolScopeConfig
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_tracking import MT5TrackedRecommendation
from app.core.models.runtime_cycle import (
    AdvancedTrackedRecommendationOutcome,
    ExcludedTrackedRecommendation,
    HistoryReadStatus,
    NettingGuardResult,
    PositionsReadStatus,
    RuntimeCycleResult,
    TrackingIssuancePersistenceOutcome,
)
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.mt5.history import compute_realized_daily_pnl
from app.mt5.persistence import MT5RolloverStatePersistence
from app.mt5.protocols import MT5ClientProtocol
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.recommendation_provenance_persistence import MT5RecommendationProvenancePersistence
from app.mt5.risk import assess_open_risk
from app.mt5.rollover import build_rollover_snapshot, compute_trading_day_key, decide_rollover, trading_day_interval
from app.mt5.tracker import advance_tracked_recommendation
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline
from app.orchestration.facts import assemble_account_risk_snapshot
from app.orchestration.final_recommendation import construct_final_recommendations
from app.orchestration.tracking_integration import construct_tracked_recommendations

_LOCK_HOLDING_STATUSES: frozenset[TradeStatus] = frozenset({TradeStatus.PENDING, TradeStatus.OPEN})
"""The only two ``TradeStatus`` values (see ``app.core.models.mt5_tracking``'s
own ``_PRE_MATCH_STATUSES``/``_POST_MATCH_STATUSES``) under which a NETTING
per-symbol lock must remain held: ``PENDING`` (no broker evidence yet) and
``OPEN`` (matched, broker position still live). ``WIN``/``LOSS``/
``BREAKEVEN`` are terminal by ``matched_position_id`` immutability;
``NOT_FILLED`` is terminal by construction (its execution window has closed
and can never be satisfied again - see ``app.mt5.matching``)."""


def _symbol_has_unresolved_tracking(tracked_by_trade_id: Mapping[str, MT5TrackedRecommendation], symbol: str) -> bool:
    return any(
        tracked.position_record.symbol == symbol and tracked.position_record.status in _LOCK_HOLDING_STATUSES
        for tracked in tracked_by_trade_id.values()
    )


def _evaluate_netting_guard(
    *,
    symbol: Symbol,
    account_position_mode: AccountPositionMode,
    positions_read_status: PositionsReadStatus,
    positions: tuple[MT5Position, ...],
    tracked_by_trade_id: Mapping[str, MT5TrackedRecommendation],
    actionable_count: int,
) -> NettingGuardResult:
    """The approved NETTING/UNKNOWN issuance invariant: at most one
    unresolved recommendation lifecycle may exist per symbol across the
    entire system before a new one may be issued.

    When ``positions_read_status`` is not ``"OK"``, this guard applies no
    netting-specific reason of its own (it cannot prove the symbol is flat,
    but it also cannot prove it is not) - existing issuance failure rules
    take over instead: ``construct_tracked_recommendations`` will itself
    correctly fail every family closed with ``SNAPSHOT_UNAVAILABLE`` once an
    unconfirmed snapshot is threaded through, exactly as it already does for
    ``HEDGING``. No new reason is invented to duplicate that existing,
    already-audited fail-closed path.
    """
    if positions_read_status == "OK" and any(position.symbol == symbol for position in positions):
        return NettingGuardResult(
            symbol=symbol,
            account_position_mode=account_position_mode,
            outcome=NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION,
        )

    if _symbol_has_unresolved_tracking(tracked_by_trade_id, symbol):
        return NettingGuardResult(
            symbol=symbol,
            account_position_mode=account_position_mode,
            outcome=NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION,
        )

    if actionable_count == 0:
        return NettingGuardResult(
            symbol=symbol, account_position_mode=account_position_mode, outcome=NettingIssuanceOutcome.NO_ACTIONABLE_RECOMMENDATIONS
        )

    if actionable_count == 1:
        return NettingGuardResult(symbol=symbol, account_position_mode=account_position_mode, outcome=NettingIssuanceOutcome.ALLOWED)

    return NettingGuardResult(
        symbol=symbol,
        account_position_mode=account_position_mode,
        outcome=NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS,
    )


def _compute_history_start(
    *, trading_day_start: Timestamp, tracked_by_trade_id: Mapping[str, MT5TrackedRecommendation]
) -> Timestamp:
    """The smallest deterministic window covering both Stage 10D's current
    trading day and every successfully-loaded tracked recommendation's own
    ``signal_time`` (Stage 10E's own caller contract - ``app.mt5.tracker``
    requires "complete history back to its genesis IN deal on every call")."""
    if not tracked_by_trade_id:
        return trading_day_start
    return min(trading_day_start, min(tracked.position_record.signal_time for tracked in tracked_by_trade_id.values()))


def _advance_all_existing_tracking(
    *,
    as_of: Timestamp,
    tracked_by_trade_id: Mapping[str, MT5TrackedRecommendation],
    deals: tuple[MT5Deal, ...],
    history_read_status: HistoryReadStatus,
    history_covers_until: Timestamp,
) -> tuple[tuple[str, MT5TrackedRecommendation], ...]:
    """Advance every successfully-loaded tracked recommendation using only
    the existing, unmodified ``advance_tracked_recommendation`` - in
    lexicographic ``trade_id`` order (mirrors ``MT5RecommendationPersistence.
    list_trade_ids()``'s own existing sort), maintaining one running claimed-
    position reservation set so a match found earlier in this same pass is
    immediately reserved for every later ``trade_id`` this cycle. No custom
    matching/PnL/expiry logic - purely deterministic sequencing over the
    existing pure function."""
    claimed: set[int] = {
        tracked.matched_position_id for tracked in tracked_by_trade_id.values() if tracked.matched_position_id is not None
    }
    results: list[tuple[str, MT5TrackedRecommendation]] = []
    for trade_id in sorted(tracked_by_trade_id):
        tracked = tracked_by_trade_id[trade_id]
        own_id = tracked.matched_position_id
        already_claimed_by_others = claimed - ({own_id} if own_id is not None else set())
        updated = advance_tracked_recommendation(
            as_of=as_of,
            tracked=tracked,
            deals=deals,
            history_read_status=history_read_status,
            history_covers_until=history_covers_until,
            already_claimed_position_ids=tuple(sorted(already_claimed_by_others)),
        )
        if updated.matched_position_id is not None:
            claimed.add(updated.matched_position_id)
        results.append((trade_id, updated))
    return tuple(results)


def _compute_cycle_outcome(
    *,
    connectivity_available: bool,
    account_risk_snapshot_assembly_ready: bool,
    any_excluded_tracking: bool,
    any_tracking_write_failure: bool,
    any_provenance_write_failure: bool,
    rollover_write_failed: bool,
    positions_read_status: PositionsReadStatus | None,
    history_read_status: HistoryReadStatus | None,
    any_netting_block: bool,
    target_symbol_facts_available: bool | None,
) -> RuntimeCycleOutcome:
    """``target_symbol_facts_available is False`` degrades the cycle exactly
    like any other confirmed-unavailable MT5 read (positions/history): the
    new-recommendation issuance path could not complete even though other
    sub-components may have succeeded. ``None`` (connectivity never reached
    symbol-facts acquisition at all) is deliberately excluded from this
    check - that path already returns ``BLOCKED`` above, never reaching this
    line, so degrading on ``None`` here would be dead/duplicate logic.
    ``True`` never degrades the cycle by itself - a healthy cycle with zero
    actionable recommendations is legitimately ``READY``, not a failure."""
    if not connectivity_available:
        return RuntimeCycleOutcome.BLOCKED
    degraded = (
        not account_risk_snapshot_assembly_ready
        or any_excluded_tracking
        or any_tracking_write_failure
        or any_provenance_write_failure
        or rollover_write_failed
        or positions_read_status != "OK"
        or history_read_status != "OK"
        or any_netting_block
        or target_symbol_facts_available is False
    )
    return RuntimeCycleOutcome.PARTIAL_DEGRADED if degraded else RuntimeCycleOutcome.READY


def run_runtime_cycle(
    *,
    client: MT5ClientProtocol,
    as_of: Timestamp,
    rollover_policy: MT5RolloverPolicyConfig,
    rollover_persistence: MT5RolloverStatePersistence,
    tracking_persistence: MT5RecommendationPersistence,
    provenance_persistence: MT5RecommendationProvenancePersistence,
    trading_cycle_config: TradingCycleConfig,
    market: MarketType,
    trade_ids: Mapping[StrategyFamily, str],
    context: MarketEvaluationContext,
    flow: FlowSupervisorResult | None = None,
    technical: TechnicalSupervisorResult | None = None,
    external: ExternalIntelligenceSupervisorResult | None = None,
    m15_market_structure: MarketStructureFeatures | None = None,
    locked_override: bool = False,
    high_impact_event_context: HighImpactEventContext | None = None,
    high_impact_event_symbol_scope_config: HighImpactEventSymbolScopeConfig | None = None,
) -> RuntimeCycleResult:
    """Run exactly one deterministic runtime cycle.

    ``as_of`` is the one caller-supplied cycle timestamp - never read from
    the wall clock here - threaded unchanged into every pure call that
    accepts ``as_of``/``evaluation_time``. ``flow``/``technical``/``external``/
    ``m15_market_structure``/``high_impact_event_context``/
    ``high_impact_event_symbol_scope_config`` are already-produced upstream
    results/static config supplied by the caller: this coordinator never
    fetches Binance/news/macro/on-chain/external-intelligence/high-impact-
    event-bridge data itself, and never derives symbol relevance policy
    itself - it is runtime (MT5) orchestration only. In particular, no file
    is ever read here: the MQL5 calendar bridge file-reader adapter
    (``app.high_impact_event_bridge``) remains strictly upstream of this
    module.
    """
    runtime_status = client.initialize()
    try:
        if runtime_status.state is not MT5ConnectivityState.AVAILABLE:
            return RuntimeCycleResult(as_of=as_of, outcome=RuntimeCycleOutcome.BLOCKED, mt5_runtime_status=runtime_status)

        account_facts = client.account_facts()
        account_position_mode = account_facts.margin_mode if account_facts is not None else None

        # --- existing tracking: load once, lexicographic trade_id order ---
        tracked_by_trade_id: dict[str, MT5TrackedRecommendation] = {}
        excluded_tracked_recommendations: list[ExcludedTrackedRecommendation] = []
        for trade_id in tracking_persistence.list_trade_ids():
            read_status, tracked = tracking_persistence.read(trade_id)
            if read_status == "VALID":
                assert tracked is not None
                tracked_by_trade_id[trade_id] = tracked
            elif read_status == "ABSENT":
                continue  # benign race: listed then removed before read - nothing to report
            else:
                excluded_tracked_recommendations.append(ExcludedTrackedRecommendation(trade_id=trade_id, read_status=read_status))

        # --- history: read once ---
        trading_day_key = compute_trading_day_key(as_of=as_of, policy=rollover_policy)
        trading_day_start, trading_day_end = trading_day_interval(trading_day_key, rollover_policy)
        history_start = _compute_history_start(trading_day_start=trading_day_start, tracked_by_trade_id=tracked_by_trade_id)
        history_read_status, deals = client.history_deals(start=history_start, end=as_of)

        # --- advance existing tracking (pure) + persist (impure) ---
        advanced_pure = _advance_all_existing_tracking(
            as_of=as_of,
            tracked_by_trade_id=tracked_by_trade_id,
            deals=deals,
            history_read_status=history_read_status,
            history_covers_until=as_of,
        )
        advanced_tracking: list[AdvancedTrackedRecommendationOutcome] = []
        advanced_by_trade_id: dict[str, MT5TrackedRecommendation] = {}
        for trade_id, updated in advanced_pure:
            persisted = tracking_persistence.write(trade_id, updated)
            advanced_tracking.append(AdvancedTrackedRecommendationOutcome(trade_id=trade_id, tracked_recommendation=updated, persisted=persisted))
            advanced_by_trade_id[trade_id] = updated

        # --- positions: read once ---
        positions_read_status, positions = client.positions()

        # --- rollover (Stage 10B, unmodified) ---
        rollover_snapshot = None
        rollover_persisted: bool | None = None
        if account_facts is not None:
            persisted_read_status, persisted_state = rollover_persistence.read()
            rollover_outcome, rollover_state = decide_rollover(
                current_trading_day_key=trading_day_key,
                current_equity=account_facts.equity,
                as_of=as_of,
                policy=rollover_policy,
                persisted_read_status=persisted_read_status,
                persisted_state=persisted_state,
            )
            rollover_snapshot = build_rollover_snapshot(
                as_of=as_of,
                current_equity=account_facts.equity,
                floating_pnl=account_facts.floating_pnl,
                outcome=rollover_outcome,
                rollover_state=rollover_state,
            )
            if rollover_state is not None and rollover_state != persisted_state:
                rollover_persisted = rollover_persistence.write(rollover_state)

        # --- realized daily PnL (Stage 10D, unmodified) - only if history read is OK ---
        realized_daily_pnl_assessment = None
        if history_read_status == "OK":
            realized_daily_pnl_assessment = compute_realized_daily_pnl(
                as_of=as_of, trading_day_key=trading_day_key, deals=deals, window_start=trading_day_start, window_end=trading_day_end
            )

        # --- symbol facts: deduplicated, at most once per unique symbol ---
        target_symbol = context.symbol
        unique_symbols: set[str] = {target_symbol}
        if positions_read_status == "OK":
            unique_symbols |= {position.symbol for position in positions}
        symbol_facts_by_symbol = {}
        for symbol in sorted(unique_symbols):
            facts = client.symbol_facts(symbol)
            if facts is not None:
                symbol_facts_by_symbol[symbol] = facts
        target_symbol_facts_available = target_symbol in symbol_facts_by_symbol

        # --- open risk (Stage 10C, unmodified) - only if positions read is OK ---
        open_risk_assessment = None
        if positions_read_status == "OK":
            open_risk_assessment = assess_open_risk(as_of=as_of, positions=positions, symbol_facts_by_symbol=symbol_facts_by_symbol)

        # --- Runtime Fact Assembly - only once all three sub-assessments exist ---
        account_risk_snapshot_assembly = None
        if rollover_snapshot is not None and realized_daily_pnl_assessment is not None and open_risk_assessment is not None:
            account_risk_snapshot_assembly = assemble_account_risk_snapshot(
                as_of=as_of,
                rollover_snapshot=rollover_snapshot,
                realized_daily_pnl_assessment=realized_daily_pnl_assessment,
                open_risk_assessment=open_risk_assessment,
            )

        # --- Decision/Risk Pipeline (Stage 5-9, unmodified) ---
        decision_risk_pipeline_result = None
        if account_risk_snapshot_assembly is not None:
            decision_risk_pipeline_result = evaluate_decision_risk_pipeline(
                flow=flow,
                technical=technical,
                external=external,
                context=context,
                evaluation_time=as_of,
                symbol_facts=symbol_facts_by_symbol.get(target_symbol),
                m15_market_structure=m15_market_structure,
                account_risk_snapshot_assembly=account_risk_snapshot_assembly,
                trading_cycle_config=trading_cycle_config,
                locked_override=locked_override,
                high_impact_event_context=high_impact_event_context,
                high_impact_event_symbol_scope_config=high_impact_event_symbol_scope_config,
            )

        # --- Final Recommendation (Stage 10C sizing, unmodified) ---
        final_recommendation_construction_result = None
        if decision_risk_pipeline_result is not None and account_facts is not None and target_symbol in symbol_facts_by_symbol:
            final_recommendation_construction_result = construct_final_recommendations(
                decision_risk_pipeline_result=decision_risk_pipeline_result,
                symbol_facts=symbol_facts_by_symbol[target_symbol],
                account_currency=account_facts.currency,
                trade_ids=trade_ids,
                as_of=as_of,
            )

        # --- NETTING/UNKNOWN issuance guard + Part E tracking creation ---
        netting_guard_result = None
        new_tracking_results: tuple = ()
        new_tracking_persistence_outcomes: list[TrackingIssuancePersistenceOutcome] = []

        if final_recommendation_construction_result is not None:
            assert account_position_mode is not None  # guaranteed: account_facts required above
            actionable_count = sum(
                1
                for family_result in final_recommendation_construction_result.family_results
                if family_result.verdict is FinalRecommendationVerdict.ACTIONABLE
            )

            if account_position_mode is AccountPositionMode.HEDGING:
                issuance_allowed = actionable_count > 0
            else:
                netting_guard_result = _evaluate_netting_guard(
                    symbol=target_symbol,
                    account_position_mode=account_position_mode,
                    positions_read_status=positions_read_status,
                    positions=positions,
                    tracked_by_trade_id=advanced_by_trade_id,
                    actionable_count=actionable_count,
                )
                issuance_allowed = netting_guard_result.outcome is NettingIssuanceOutcome.ALLOWED

            if issuance_allowed:
                new_tracking_results = construct_tracked_recommendations(
                    final_recommendation_construction_result=final_recommendation_construction_result,
                    as_of=as_of,
                    market=market,
                    pre_existing_positions_read_status=positions_read_status,
                    pre_existing_positions=positions,
                )
                for result in new_tracking_results:
                    tracking_persisted = False
                    provenance_persisted = False
                    if result.tracking_creation_result.outcome is MT5TrackedRecommendationCreationOutcome.CREATED:
                        tracked = result.tracking_creation_result.tracked_recommendation
                        assert tracked is not None
                        tracking_persisted = tracking_persistence.write(result.trade_id, tracked)
                        provenance_persisted = provenance_persistence.write(result.trade_id, result.provenance)
                    new_tracking_persistence_outcomes.append(
                        TrackingIssuancePersistenceOutcome(
                            trade_id=result.trade_id,
                            tracking_creation_outcome=result.tracking_creation_result.outcome,
                            tracking_persisted=tracking_persisted,
                            provenance_persisted=provenance_persisted,
                        )
                    )

        outcome = _compute_cycle_outcome(
            connectivity_available=True,
            account_risk_snapshot_assembly_ready=account_risk_snapshot_assembly is not None,
            any_excluded_tracking=bool(excluded_tracked_recommendations),
            any_tracking_write_failure=(
                any(not entry.persisted for entry in advanced_tracking)
                or any(
                    entry.tracking_creation_outcome is MT5TrackedRecommendationCreationOutcome.CREATED and not entry.tracking_persisted
                    for entry in new_tracking_persistence_outcomes
                )
            ),
            any_provenance_write_failure=any(
                entry.tracking_creation_outcome is MT5TrackedRecommendationCreationOutcome.CREATED and not entry.provenance_persisted
                for entry in new_tracking_persistence_outcomes
            ),
            rollover_write_failed=rollover_persisted is False,
            positions_read_status=positions_read_status,
            history_read_status=history_read_status,
            any_netting_block=(
                netting_guard_result is not None
                and netting_guard_result.outcome
                not in (NettingIssuanceOutcome.ALLOWED, NettingIssuanceOutcome.NO_ACTIONABLE_RECOMMENDATIONS)
            ),
            target_symbol_facts_available=target_symbol_facts_available,
        )

        return RuntimeCycleResult(
            as_of=as_of,
            outcome=outcome,
            mt5_runtime_status=runtime_status,
            account_facts=account_facts,
            account_position_mode=account_position_mode,
            positions_read_status=positions_read_status,
            history_read_status=history_read_status,
            target_symbol_facts_available=target_symbol_facts_available,
            rollover_snapshot=rollover_snapshot,
            rollover_persisted=rollover_persisted,
            realized_daily_pnl_assessment=realized_daily_pnl_assessment,
            open_risk_assessment=open_risk_assessment,
            account_risk_snapshot_assembly=account_risk_snapshot_assembly,
            decision_risk_pipeline_result=decision_risk_pipeline_result,
            final_recommendation_construction_result=final_recommendation_construction_result,
            netting_guard_result=netting_guard_result,
            new_tracking_results=new_tracking_results,
            new_tracking_persistence_outcomes=tuple(new_tracking_persistence_outcomes),
            advanced_tracking=tuple(advanced_tracking),
            excluded_tracked_recommendations=tuple(excluded_tracked_recommendations),
        )
    finally:
        client.shutdown()


__all__ = ["run_runtime_cycle"]
