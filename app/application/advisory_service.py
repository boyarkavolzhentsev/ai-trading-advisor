"""Application Service (Final Runtime Integration, Application layer).

The one transport-neutral service sitting directly above
``ProductionAdvisoryComposer`` (Stage 0D). Owns:

- capturing exactly one ``datetime.now(UTC)`` per ``create_advisory`` call
- deterministic derivation of caller-owned ``trade_ids`` from a caller-owned
  ``logical_cycle_id`` (``app.application.identity`` - never generates one
  itself)
- delegating the entire cycle to ``ProductionAdvisoryComposer.run_cycle``
- mapping the returned ``ProductionAdvisoryCycleResult``/raised Stage0D
  exception into the stable ``AdvisoryResponse`` DTO / typed Application
  error (``app.application.dto``/``app.application.errors``)

Owns NOTHING already owned by Stage0D or any closed trading/runtime module:
never touches MT5/Binance/the calendar bridge/OpenAI directly, never
reimplements Judge/Policy/Setup/Risk/Portfolio/Session/Final-Recommendation/
NETTING-issuance logic - every fact this module reports is read, unchanged,
from an already-produced typed result. The only new logic this module adds
is presentation-level: which existing typed fact to surface first for one
``StrategyFamily`` (see ``derive_no_trade_reason``) and whether an
``ACTIONABLE`` family's recommendation was genuinely issued (see
``is_issuable``) - both are pure functions of already-existing fields, never
a new business judgment.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from app.application.cycle_receipt import CycleReceiptClaimResult, CycleReceiptPersistence
from app.application.dto import (
    AdvisoryResponse,
    ApplicationAdvisoryStatus,
    ExplanationDTO,
    IssuanceFailureReason,
    IssuancePersistenceDTO,
    NoTradeCode,
    NoTradeReasonDTO,
    NoTradeStage,
    OperationalDiagnosticsDTO,
    RecommendationDTO,
    RecommendationNarrativeDTO,
    TradingDataQualityDTO,
)
from app.application.errors import (
    ApplicationAdvisoryError,
    ApplicationStateError,
    DuplicateCycleError,
    InternalApplicationError,
)
from app.application.identity import derive_trade_ids, validate_logical_cycle_id
from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.explanation import ExplanationProviderStatus
from app.core.enums.final_recommendation import FinalRecommendationBlockReason, FinalRecommendationVerdict
from app.core.enums.high_impact_event import HighImpactEventVerdict
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict
from app.core.enums.portfolio import PortfolioBlockReason
from app.core.enums.risk_gate import RiskBlockReason
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyOutcome
from app.core.enums.session_gate import SessionBlockReason
from app.core.enums.setup_construction import SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.final_recommendation import FinalRecommendation
from app.core.models.runtime_cycle import RuntimeCycleResult
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError, ProductionAdvisoryLifecycleError
from app.production_advisory.result import ProductionAdvisoryCycleOutcome, ProductionAdvisoryCycleResult

_JUDGE_MIRRORED_POLICY_REASONS = frozenset(
    {PolicyBlockReason.JUDGE_OUTCOME_MIXED, PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE}
)
"""The two ``PolicyBlockReason`` members that reify a non-``DIRECTIONAL``
``JudgeOutcome`` - Judge itself has no ``BLOCKED`` verdict of its own, so
these are the sole typed signal that a family's terminal cause is genuinely
Judge-stage, not Policy-stage (see ``NoTradeStage.JUDGE`` vs
``NoTradeStage.POLICY``, and the approved corrective design closure, "16.
JUDGE VS POLICY")."""


def _find_by_family(items: Iterable, family: StrategyFamily):
    for item in items:
        if item.family is family:
            return item
    return None


def derive_no_trade_reason(family: StrategyFamily, runtime_cycle_result: RuntimeCycleResult) -> NoTradeReasonDTO | None:
    """Walk one ``StrategyFamily`` through the pipeline in its own exact run
    order (EVALUATION -> JUDGE -> POLICY -> SETUP -> EVENT -> RISK ->
    PORTFOLIO -> SESSION -> FINAL) and return the FIRST genuine terminal
    cause, or ``None`` if no per-family no-trade fact exists yet (the family
    is still ``ACTIONABLE`` as of Final Recommendation, or the pipeline never
    reached far enough to produce one this cycle - e.g.
    ``DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK``).

    Every later stage's own "upstream propagation" reason
    (``PolicyBlockReason`` aside - see ``_JUDGE_MIRRORED_POLICY_REASONS``) is
    a typed mirror of an earlier stage's genuine block
    (``RiskBlockReason.POLICY_NOT_ELIGIBLE``,
    ``PortfolioBlockReason.RISK_NOT_ELIGIBLE``,
    ``SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE``,
    ``FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE``) - each is
    provably unreachable here precisely because the earlier, genuine stage
    already returned first (proved for every one of the four mirror reasons
    in the approved corrective design closure, section E). Never infers
    anything from ``ExplanationResult``/narrative text.
    """
    drp = runtime_cycle_result.decision_risk_pipeline_result
    if drp is None:
        return None  # whole cycle never reached the pipeline (SERVICE_UNAVAILABLE) - not a per-family fact

    router_result = drp.strategy_setup_result.strategy_policy_result.strategy_judge_result.strategy_router_result
    eligibility_entry = _find_by_family(router_result.eligibility, family)
    assert eligibility_entry is not None  # StrategyRouterResult covers every StrategyFamily, always
    if not eligibility_entry.eligible:
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.EVALUATION, codes=eligibility_entry.ineligibility_reasons)

    policy_result = _find_by_family(drp.strategy_setup_result.strategy_policy_result.family_results, family)
    assert policy_result is not None  # Policy covers every Router-eligible family
    if policy_result.verdict is PolicyFamilyVerdict.BLOCKED:
        stage = NoTradeStage.JUDGE if policy_result.reasons and policy_result.reasons[0] in _JUDGE_MIRRORED_POLICY_REASONS else NoTradeStage.POLICY
        return NoTradeReasonDTO(strategy_family=family, stage=stage, codes=policy_result.reasons)

    setup_result = _find_by_family(drp.strategy_setup_result.family_results, family)
    assert setup_result is not None  # Setup Construction covers every Policy-eligible family
    if setup_result.outcome is SetupConstructionOutcome.BLOCKED:
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.SETUP, codes=setup_result.reasons)

    if drp.high_impact_event_risk_result is not None:
        event_result = _find_by_family(drp.high_impact_event_risk_result.family_results, family)
        if event_result is not None and event_result.verdict is HighImpactEventVerdict.BLOCKED:
            return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.EVENT, codes=event_result.reasons)

    if drp.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK or drp.strategy_session_result is None:
        # Runtime Fact Assembly was not READY this cycle - Stage 7 onward
        # never ran for ANY family. This is a whole-cycle fact (already
        # visible via ApplicationAdvisoryStatus.DEGRADED/
        # TradingDataQualityDTO.runtime_outcome), not a per-family typed
        # reason - no RiskFamilyResult exists to report, so none is invented.
        return None

    strategy_portfolio_result = drp.strategy_session_result.strategy_portfolio_result
    risk_result = _find_by_family(strategy_portfolio_result.strategy_risk_result.family_results, family)
    assert risk_result is not None
    if risk_result.reasons and risk_result.reasons != (RiskBlockReason.POLICY_NOT_ELIGIBLE,):
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.RISK, codes=risk_result.reasons)

    portfolio_result = _find_by_family(strategy_portfolio_result.family_results, family)
    assert portfolio_result is not None
    if portfolio_result.reasons and portfolio_result.reasons != (PortfolioBlockReason.RISK_NOT_ELIGIBLE,):
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.PORTFOLIO, codes=portfolio_result.reasons)

    session_result = _find_by_family(drp.strategy_session_result.family_results, family)
    assert session_result is not None
    if session_result.reasons and session_result.reasons != (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,):
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.SESSION, codes=session_result.reasons)

    final_construction = runtime_cycle_result.final_recommendation_construction_result
    if final_construction is None:
        return None
    final_result = _find_by_family(final_construction.family_results, family)
    if final_result is None:
        return None
    if final_result.reasons and final_result.reasons != (FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE,):
        return NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.FINAL, codes=final_result.reasons)

    if final_result.verdict is not FinalRecommendationVerdict.ACTIONABLE:
        # Every genuine block reason at every stage is provably exhaustive
        # (see this function's own docstring) - reaching here means either
        # a pipeline change broke that invariant, or a genuine programming
        # defect. Never silently report "no reason" for a BLOCKED family.
        raise InternalApplicationError(
            f"family {family}: FinalRecommendationFamilyResult is BLOCKED but no genuine "
            "no-trade reason was found anywhere in the precedence walk"
        )

    return None  # ACTIONABLE - see is_issuable() for whether it is genuinely issuable


def is_issuable(trade_id: str, runtime_cycle_result: RuntimeCycleResult) -> bool:
    """Whether ``trade_id`` was genuinely tracked AND persisted this cycle -
    the sole issuance authority, per the approved corrective design closure,
    "11. ISSUABLE RECOMMENDATION AUTHORITY" / "G. FINAL ISSUABLE-RECOMMENDATION
    RULE" (pre-commit issuance/degraded-cause review). Never reconstructs the
    NETTING/HEDGING rule itself: this reads only ``RuntimeCycleResult.
    new_tracking_persistence_outcomes``, the downstream runtime fact Part F's
    own issuance guard and Part E's own tracking-creation attempt already
    produced.

    ``tracking_creation_outcome is CREATED`` alone is NOT sufficient:
    ``TrackingIssuancePersistenceOutcome``'s own docstring proves
    ``tracking_persisted``/``provenance_persisted`` are attempted
    independently after a ``CREATED`` outcome, and all four combinations are
    representable - a ``CREATED`` recommendation whose ``tracking_persisted``
    write itself failed has no durable tracking record at all and must never
    be exposed as operator-facing output (see the pre-commit review, "3.
    REQUIRED TRACKING SAFETY INVARIANT"). ``provenance_persisted`` is
    deliberately NOT part of this gate (see "4. PROVENANCE FAILURE POLICY" -
    a provenance-only failure still leaves a real, trackable position and
    must not be hidden from the operator; it is instead surfaced via
    ``OperationalDiagnosticsDTO.issuance_persistence`` and the cycle already
    reports ``ApplicationAdvisoryStatus.DEGRADED`` for it, since
    ``RuntimeCycleOutcome`` itself degrades on any provenance write failure -
    see ``app.orchestration.runtime_cycle._compute_cycle_outcome``'s own
    ``any_provenance_write_failure`` input)."""
    return any(
        outcome.trade_id == trade_id
        and outcome.tracking_creation_outcome is MT5TrackedRecommendationCreationOutcome.CREATED
        and outcome.tracking_persisted is True
        for outcome in runtime_cycle_result.new_tracking_persistence_outcomes
    )


def _derive_issuance_reason(trade_id: str, runtime_cycle_result: RuntimeCycleResult) -> NoTradeCode:
    """Exact typed cause an ``ACTIONABLE`` family was not genuinely issued -
    never a generic invented string. Prefers the symbol-wide
    ``NettingGuardResult`` cause when present and non-``ALLOWED`` (NETTING/
    UNKNOWN suppression); otherwise the per-``trade_id`` outcome:
    ``MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE`` verbatim
    when creation itself never happened, or
    ``IssuanceFailureReason.TRACKING_PERSISTENCE_FAILED`` when creation
    succeeded (``CREATED``) but ``tracking_persisted`` is ``False`` - never
    ``CREATED`` itself, which would self-contradictorily report a success
    fact as a block cause (see ``IssuanceFailureReason``'s own docstring)."""
    netting = runtime_cycle_result.netting_guard_result
    if netting is not None and netting.outcome is not NettingIssuanceOutcome.ALLOWED:
        return netting.outcome
    for outcome in runtime_cycle_result.new_tracking_persistence_outcomes:
        if outcome.trade_id == trade_id:
            if outcome.tracking_creation_outcome is MT5TrackedRecommendationCreationOutcome.CREATED:
                return IssuanceFailureReason.TRACKING_PERSISTENCE_FAILED
            return outcome.tracking_creation_outcome
    raise InternalApplicationError(
        f"trade_id {trade_id!r} is ACTIONABLE and not issuable, but no typed issuance cause "
        "(NettingGuardResult or MT5TrackedRecommendationCreationOutcome) was found"
    )


def _map_recommendation(recommendation: FinalRecommendation) -> RecommendationDTO:
    return RecommendationDTO(
        trade_id=recommendation.trade_id,
        strategy_family=recommendation.family,
        symbol=recommendation.symbol,
        direction=recommendation.direction,
        entry_price=recommendation.entry_price,
        stop_loss=recommendation.stop_loss,
        take_profit_levels=recommendation.take_profit_levels,
        approved_volume=recommendation.approved_volume,
        approved_risk_amount=recommendation.approved_risk_amount,
        account_currency=recommendation.account_currency,
        signal_time=recommendation.signal_time,
        valid_until=recommendation.valid_until,
    )


def map_recommendations(
    cycle: ProductionAdvisoryCycleResult,
) -> tuple[tuple[RecommendationDTO, ...], tuple[NoTradeReasonDTO, ...]]:
    """One pass over every ``StrategyFamily``, in canonical declaration
    order, producing both the issuable-recommendation tuple and the
    no-trade-reason tuple together - the two are complementary outcomes of
    the same per-family walk, never computed from two independent
    re-derivations of the pipeline. Empty on the
    ``ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE`` early-return shape
    (``decision_risk_pipeline_result``/``final_recommendation_construction_result``
    are both ``None`` there - handled safely by ``derive_no_trade_reason``'s
    own early ``None`` return, never by unwrapping a missing field)."""
    runtime_cycle_result = cycle.runtime_cycle_result
    recommendations: list[RecommendationDTO] = []
    no_trade_reasons: list[NoTradeReasonDTO] = []

    if cycle.outcome is ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE:
        return (), ()

    final_construction = runtime_cycle_result.final_recommendation_construction_result

    for family in StrategyFamily:
        no_trade = derive_no_trade_reason(family, runtime_cycle_result)
        if no_trade is not None:
            no_trade_reasons.append(no_trade)
            continue

        if final_construction is None:
            continue  # BLOCKED_BEFORE_RISK or symbol-facts-unavailable this cycle - no per-family fact available

        final_result = _find_by_family(final_construction.family_results, family)
        if final_result is None:
            continue

        if final_result.verdict is not FinalRecommendationVerdict.ACTIONABLE:
            raise InternalApplicationError(
                f"family {family}: BLOCKED FinalRecommendationFamilyResult reached map_recommendations "
                "without a no-trade reason - derive_no_trade_reason's own precedence walk should have caught this"
            )

        recommendation = final_result.recommendation
        assert recommendation is not None  # guaranteed by FinalRecommendationFamilyResult's own ACTIONABLE invariant

        if is_issuable(recommendation.trade_id, runtime_cycle_result):
            recommendations.append(_map_recommendation(recommendation))
        else:
            # ACTIONABLE but not genuinely issued this cycle - never silently
            # dropped, always surfaced with its exact typed cause.
            issuance_code = _derive_issuance_reason(recommendation.trade_id, runtime_cycle_result)
            no_trade_reasons.append(NoTradeReasonDTO(strategy_family=family, stage=NoTradeStage.ISSUANCE, codes=(issuance_code,)))

    return tuple(recommendations), tuple(no_trade_reasons)


def derive_application_status(
    cycle: ProductionAdvisoryCycleResult, recommendations: tuple[RecommendationDTO, ...]
) -> ApplicationAdvisoryStatus:
    """Exact precedence: SERVICE_UNAVAILABLE > DEGRADED > READY (>=1 issuable
    recommendation) > NO_TRADE. ``recommendations`` is computed independently
    (see ``map_recommendations``) - a DEGRADED cycle may still carry one or
    more recommendations; status describes cycle quality, never merely
    whether a trade exists."""
    if cycle.outcome is ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE:
        return ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE
    if cycle.runtime_cycle_result.outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED:
        return ApplicationAdvisoryStatus.DEGRADED
    if recommendations:
        return ApplicationAdvisoryStatus.READY
    return ApplicationAdvisoryStatus.NO_TRADE


def map_trading_data_quality(cycle: ProductionAdvisoryCycleResult) -> TradingDataQualityDTO:
    """Small, honest trading-evidence-quality summary - deliberately omits
    Flow/Technical evidence quality (unaudited) and
    ``FlowRealtimeBootstrapHealth`` (operational health, not trading
    evidence - see ``map_operational_diagnostics``).

    ``account_risk_snapshot_ready``/``account_risk_snapshot_block_reasons``
    close the "whole-cycle DEGRADED cause" gap identified in the pre-commit
    issuance/degraded-cause review: ``RuntimeCycleResult.
    account_risk_snapshot_assembly`` is read directly (never re-derived) so a
    consumer can distinguish "Runtime Fact Assembly was never even
    attempted this cycle" (``account_risk_snapshot_assembly is None`` -
    check ``positions_read_status``/``history_read_status`` for the raw
    upstream cause) from "it was attempted and genuinely blocked"
    (``account_risk_snapshot_assembly.outcome is BLOCKED``, with its own
    ``reasons`` surfaced verbatim) - never fabricated as a per-family
    ``NoTradeReasonDTO`` (see ``derive_no_trade_reason``'s own early
    ``BLOCKED_BEFORE_RISK``/``drp is None`` return)."""
    runtime_cycle_result = cycle.runtime_cycle_result
    drp = runtime_cycle_result.decision_risk_pipeline_result
    calendar_data_quality = None
    if drp is not None and drp.high_impact_event_risk_result is not None and drp.high_impact_event_risk_result.family_results:
        # One shared HighImpactEventContext produces this cycle's gate run -
        # every per-family entry carries the identical data_quality fact.
        calendar_data_quality = drp.high_impact_event_risk_result.family_results[0].data_quality

    assembly = runtime_cycle_result.account_risk_snapshot_assembly
    account_risk_snapshot_ready = assembly is not None and assembly.outcome is RuntimeFactAssemblyOutcome.READY
    account_risk_snapshot_block_reasons = assembly.reasons if assembly is not None else ()

    return TradingDataQualityDTO(
        runtime_outcome=runtime_cycle_result.outcome,
        mt5_connectivity_state=runtime_cycle_result.mt5_runtime_status.state,
        positions_read_status=runtime_cycle_result.positions_read_status,
        history_read_status=runtime_cycle_result.history_read_status,
        technical_fetch_failed_timeframes=tuple(failure.timeframe for failure in cycle.technical_fetch_failures),
        calendar_data_quality=calendar_data_quality,
        account_risk_snapshot_ready=account_risk_snapshot_ready,
        account_risk_snapshot_block_reasons=account_risk_snapshot_block_reasons,
    )


def map_operational_diagnostics(cycle: ProductionAdvisoryCycleResult) -> OperationalDiagnosticsDTO:
    """Operational health only - never labeled or consulted as trading
    readiness (``FlowRealtimeBootstrapHealth``'s own docstring).
    ``issuance_persistence`` is a verbatim, unfiltered copy of every
    ``TrackingIssuancePersistenceOutcome`` this cycle produced - a
    provenance-write failure remains visible here even for a trade_id that
    is still exposed in ``AdvisoryResponse.recommendations``."""
    health = cycle.flow_health
    runtime_cycle_result = cycle.runtime_cycle_result
    issuance_persistence = tuple(
        IssuancePersistenceDTO(
            trade_id=outcome.trade_id,
            tracking_creation_outcome=outcome.tracking_creation_outcome,
            tracking_persisted=outcome.tracking_persisted,
            provenance_persisted=outcome.provenance_persisted,
        )
        for outcome in runtime_cycle_result.new_tracking_persistence_outcomes
    )
    return OperationalDiagnosticsDTO(
        flow_market_stream_status=health.market.status,
        flow_order_book_stream_status=health.order_book.status,
        flow_open_interest_last_success_at=health.open_interest_last_success_at,
        llm_enabled=cycle.llm_enabled,
        llm_provider_status=cycle.explanation_result.provider_status,
        cycle_duration_seconds=cycle.cycle_duration_seconds,
        issuance_persistence=issuance_persistence,
    )


def map_explanation(cycle: ProductionAdvisoryCycleResult) -> ExplanationDTO:
    """Presentation-only content, sourced exclusively from
    ``ExplanationResult`` - never consulted for, and never able to
    influence, any ``RecommendationDTO``/``NoTradeReasonDTO``/
    ``ApplicationAdvisoryStatus`` field."""
    explanation_result = cycle.explanation_result
    narratives = tuple(
        RecommendationNarrativeDTO(
            trade_id=narrative.trade_id,
            strategy_family=narrative.family,
            narrative=narrative.narrative,
            cited_fact_ids=narrative.cited_fact_ids,
        )
        for narrative in explanation_result.recommendation_explanations
    )
    return ExplanationDTO(
        headline=explanation_result.headline,
        cycle_summary=explanation_result.cycle_summary,
        no_trade_explanation=explanation_result.no_trade_explanation,
        warnings=explanation_result.warnings,
        data_quality_notes=explanation_result.data_quality_notes,
        risk_notes=explanation_result.risk_notes,
        provider_status=explanation_result.provider_status,
        llm_enabled=cycle.llm_enabled,
        deterministic_fallback_used=explanation_result.provider_status is not ExplanationProviderStatus.LLM_SUCCESS,
        recommendation_narratives=narratives,
    )


def map_advisory_response(logical_cycle_id: str, cycle: ProductionAdvisoryCycleResult) -> AdvisoryResponse:
    """The single mapping entry point: ``ProductionAdvisoryCycleResult`` ->
    ``AdvisoryResponse``. Every field is produced by one of this module's
    other pure mapping helpers - this function only assembles them."""
    recommendations, no_trade_reasons = map_recommendations(cycle)
    status = derive_application_status(cycle, recommendations)
    return AdvisoryResponse(
        logical_cycle_id=logical_cycle_id,
        as_of=cycle.as_of,
        symbol=cycle.symbol,
        status=status,
        recommendations=recommendations,
        no_trade_reasons=no_trade_reasons,
        data_quality=map_trading_data_quality(cycle),
        diagnostics=map_operational_diagnostics(cycle),
        explanation=map_explanation(cycle),
    )


class ApplicationAdvisoryService:
    """Transport-neutral façade above ``ProductionAdvisoryComposer`` - the
    one shared process-level advisory entry point future FastAPI/Telegram
    adapters will both call into. Adds no composition-lifecycle state of its
    own: ``ProductionAdvisoryComposer``'s own NEW/STARTED/STOPPED state
    machine remains the single source of truth for that.

    Owns cycle-level request idempotency instead (the corrective "CYCLE-LEVEL
    IDEMPOTENCY" design closure): ``logical_cycle_id`` denotes ONE logical
    advisory attempt, and this is the one layer that knows about
    ``logical_cycle_id`` at all - ``ProductionAdvisoryComposer.run_cycle``
    only ever sees the derived ``trade_ids`` mapping. See
    ``app.application.cycle_receipt`` for why a single atomic claim (never a
    STARTED->COMPLETED transition, never a rewrite, never a response replay)
    is the whole mechanism.
    """

    def __init__(self, *, composer: ProductionAdvisoryComposer, cycle_receipt_persistence: CycleReceiptPersistence) -> None:
        self._composer = composer
        self._cycle_receipt_persistence = cycle_receipt_persistence

    async def startup(self) -> None:
        try:
            await self._composer.startup()
        except ProductionAdvisoryLifecycleError as exc:
            raise ApplicationStateError(str(exc)) from exc

    async def shutdown(self) -> None:
        await self._composer.shutdown()

    async def create_advisory(self, *, logical_cycle_id: str) -> AdvisoryResponse:
        """Run at most one fresh Stage0D cycle for ``logical_cycle_id``,
        ever. Never caches, never generates an identity, never retries
        automatically on a duplicate. The sole V1 advisory-creation method.

        Cycle-level idempotency: ``logical_cycle_id`` is atomically claimed
        (``CycleReceiptPersistence.claim``) before the composer is ever
        called. A claim of ``ALREADY_EXISTS`` raises ``DuplicateCycleError``
        immediately, with no composer call at all - regardless of whether a
        prior attempt for this same id returned ``READY``/``NO_TRADE``/
        ``DEGRADED``/``SERVICE_UNAVAILABLE``, raised, or crashed before
        returning anything. ``colliding_trade_ids=()`` is used deliberately:
        a receipt-level duplicate has no persisted trade_id collision to
        report (that is the separate, still-active Stage0D/
        ``ProductionAdvisoryComposer._reject_if_duplicate_cycle`` guard's own
        concern - see that method's docstring) - no trade id is ever
        fabricated merely to populate this field.

        The claim uses the exact same ``as_of`` this method captures for the
        cycle itself (never a second wall-clock read) - see
        ``test_advisory_service_never_reads_wall_clock_outside_create_advisory``.

        A claim failure *before* exclusive creation succeeds (e.g. the
        receipt directory could not be created, or a permissions error -
        see ``CycleReceiptPersistence.claim``'s own docstring) is a genuine,
        unexpected persistence error, never a caller-input problem and never
        a duplicate: it is mapped here to a sanitized ``InternalApplicationError``
        (never ``str(exc)``, which could otherwise carry the receipt
        directory's absolute filesystem path) - mirroring this same method's
        own existing catch-all around ``composer.run_cycle`` below. A failure
        writing/fsyncing the receipt body *after* exclusive creation already
        succeeded is not an error at all from this method's perspective:
        ``CycleReceiptPersistence.claim`` itself already swallows that case
        and still returns ``CREATED`` - existence is the only fact that
        matters (see its own docstring).
        """
        validate_logical_cycle_id(logical_cycle_id)
        trade_ids = derive_trade_ids(logical_cycle_id)
        as_of = datetime.now(UTC)

        try:
            claim_result = self._cycle_receipt_persistence.claim(logical_cycle_id, accepted_at=as_of)
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary, sanitized message only
            raise InternalApplicationError("cycle receipt claim failed unexpectedly") from exc

        if claim_result is CycleReceiptClaimResult.ALREADY_EXISTS:
            raise DuplicateCycleError(logical_cycle_id=logical_cycle_id, colliding_trade_ids=())

        try:
            cycle = await self._composer.run_cycle(as_of=as_of, trade_ids=trade_ids)
        except ProductionAdvisoryDuplicateCycleError as exc:
            raise DuplicateCycleError(logical_cycle_id=logical_cycle_id, colliding_trade_ids=exc.colliding_trade_ids) from exc
        except ProductionAdvisoryLifecycleError as exc:
            raise ApplicationStateError(str(exc)) from exc
        except ValueError as exc:
            # Stage0D's own trade-ID-coverage guard - unreachable given a
            # complete derive_trade_ids() mapping; occurring anyway is an
            # Application-layer defect, never caller input.
            raise InternalApplicationError(
                "advisory cycle rejected the derived trade_ids mapping - this indicates an "
                "Application-layer identity-derivation defect, not invalid caller input"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary, sanitized message only
            raise InternalApplicationError("advisory cycle failed unexpectedly") from exc

        try:
            return map_advisory_response(logical_cycle_id, cycle)
        except ApplicationAdvisoryError:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all boundary, sanitized message only
            raise InternalApplicationError("advisory response mapping failed unexpectedly") from exc


__all__ = [
    "ApplicationAdvisoryService",
    "derive_application_status",
    "derive_no_trade_reason",
    "is_issuable",
    "map_advisory_response",
    "map_explanation",
    "map_operational_diagnostics",
    "map_recommendations",
    "map_trading_data_quality",
]
