"""Shared fixture builders for ``app.application`` tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.

Every nested pipeline container model (``StrategyRouterResult``,
``StrategyJudgeResult``, ``StrategyPolicyResult``, ``StrategySetupResult``,
``HighImpactEventRiskResult``, ``StrategyRiskResult``,
``StrategyPortfolioResult``, ``StrategySessionResult``,
``DecisionRiskPipelineResult``, ``FinalRecommendationConstructionResult``,
``RuntimeCycleResult``) is built via ``model_construct`` (bypassing pydantic
validation) rather than each model's own real constructor: the mapping code
under test (``app.application.advisory_service``) only ever reads
already-produced fields via a linear per-family search - it never
re-validates cross-family coverage/ordering - so these fixtures only need to
carry the one family a given test is asking about at each stage, never the
full cross-validated 4-family invariant set every real Stage 5-9 component's
own test suite already exercises independently.

Because ``derive_no_trade_reason`` returns as soon as it finds a family's
first genuine block, a fixture for a given stage only needs to populate
containers up to and including that stage - later containers can be left
empty (never accessed).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.application.cycle_receipt import CycleReceiptClaimResult
from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.explanation import ExplanationContentStatus, ExplanationProviderStatus
from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventVerdict
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.risk_gate import RiskFamilyVerdict
from app.core.enums.session_gate import SessionFamilyVerdict
from app.core.enums.setup_construction import SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.explanation import ExplanationResult
from app.core.models.final_recommendation import (
    FinalRecommendation,
    FinalRecommendationConstructionResult,
    FinalRecommendationFamilyResult,
)
from app.core.models.high_impact_event import HighImpactEventFamilyResult, HighImpactEventRiskResult
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.core.models.policy_gate_result import PolicyFamilyResult, StrategyPolicyResult
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult
from app.core.models.risk_gate_result import RiskFamilyResult, StrategyRiskResult
from app.core.models.runtime_cycle import NettingGuardResult, RuntimeCycleResult, TrackingIssuancePersistenceOutcome
from app.core.models.session_result import SessionFamilyResult, StrategySessionResult
from app.core.models.setup_construction import CandidateTradeSetup, SetupConstructionResult
from app.core.models.stream_health import StreamHealth
from app.core.models.strategy_judge_result import StrategyJudgeResult
from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult
from app.flow.open_interest_poller import TaskHealth, TaskState
from app.flow.realtime_bootstrap import FlowRealtimeBootstrapHealth
from app.production_advisory.result import ProductionAdvisoryCycleOutcome, ProductionAdvisoryCycleResult

AS_OF = datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 1, 2, 18, 0, 0, tzinfo=UTC)
SYMBOL = "EURUSD"


class FakeCycleReceiptPersistence:
    """In-memory stand-in for ``CycleReceiptPersistence`` - same one-method
    surface (``claim``), an in-memory ``set`` instead of real files. Correct
    for unit tests that exercise ``ApplicationAdvisoryService`` error-mapping/
    clock-ownership behavior without real file I/O; restart/corruption/
    concurrency scenarios use the real, file-backed ``CycleReceiptPersistence``
    instead (see ``tests/test_application_cycle_idempotency.py``)."""

    def __init__(self) -> None:
        self._claimed: set[str] = set()
        self.claim_calls: list[str] = []

    def claim(self, logical_cycle_id: str, *, accepted_at: object) -> CycleReceiptClaimResult:
        self.claim_calls.append(logical_cycle_id)
        if logical_cycle_id in self._claimed:
            return CycleReceiptClaimResult.ALREADY_EXISTS
        self._claimed.add(logical_cycle_id)
        return CycleReceiptClaimResult.CREATED


class _SetupResultView:
    """Attribute-shape stand-in for ``StrategySetupResult`` - carries only
    ``strategy_policy_result``/``family_results``, the two attributes
    ``derive_no_trade_reason`` reads."""

    def __init__(self, strategy_policy_result: StrategyPolicyResult, family_results: tuple[SetupConstructionResult, ...]) -> None:
        self.strategy_policy_result = strategy_policy_result
        self.family_results = family_results


def eligibility_entry(family: StrategyFamily, *, eligible: bool = True, reasons: tuple = ()) -> StrategyEligibilityEntry:
    return StrategyEligibilityEntry(family=family, eligible=eligible, ineligibility_reasons=reasons)


def router_result(entries: tuple[StrategyEligibilityEntry, ...]) -> StrategyRouterResult:
    return StrategyRouterResult.model_construct(
        market_evaluation=None, outcome=None, eligibility=entries, eligible_families=tuple(e.family for e in entries if e.eligible)
    )


def judge_result(router: StrategyRouterResult) -> StrategyJudgeResult:
    return StrategyJudgeResult.model_construct(strategy_router_result=router, family_results=())


def policy_family_result(
    family: StrategyFamily, *, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW, reasons: tuple = ()
) -> PolicyFamilyResult:
    return PolicyFamilyResult.model_construct(family=family, verdict=verdict, reasons=reasons, quality_violations=())


def policy_result(judge: StrategyJudgeResult, family_results: tuple[PolicyFamilyResult, ...]) -> StrategyPolicyResult:
    return StrategyPolicyResult.model_construct(strategy_judge_result=judge, outcome=None, family_results=family_results)


def default_setup(family: StrategyFamily, *, symbol: str = SYMBOL) -> CandidateTradeSetup:
    return CandidateTradeSetup(
        family=family,
        direction=TradeDirection.LONG,
        symbol=symbol,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0900"),
        take_profit_levels=(),
        risk_per_unit=Decimal("0.0100"),
        signal_time=AS_OF,
        valid_until=VALID_UNTIL,
    )


def setup_family_result(
    family: StrategyFamily, *, outcome=SetupConstructionOutcome.CONSTRUCTED, reasons: tuple = (), setup: CandidateTradeSetup | None = None
) -> SetupConstructionResult:
    if outcome is SetupConstructionOutcome.CONSTRUCTED and setup is None:
        setup = default_setup(family)
    return SetupConstructionResult.model_construct(family=family, outcome=outcome, setup=setup, reasons=reasons)


def setup_result(policy: StrategyPolicyResult, family_results: tuple[SetupConstructionResult, ...]) -> _SetupResultView:
    return _SetupResultView(policy, family_results)


def event_family_result(
    family: StrategyFamily,
    *,
    verdict: HighImpactEventVerdict = HighImpactEventVerdict.ALLOWED,
    reasons: tuple = (),
    next_safe_time=None,
    data_quality: HighImpactEventDataQuality = HighImpactEventDataQuality.FRESH,
) -> HighImpactEventFamilyResult:
    return HighImpactEventFamilyResult(
        family=family, verdict=verdict, relevant_events=(), reasons=reasons, next_safe_time=next_safe_time, data_quality=data_quality
    )


def event_result(family_results: tuple[HighImpactEventFamilyResult, ...]) -> HighImpactEventRiskResult:
    return HighImpactEventRiskResult.model_construct(as_of=AS_OF, family_results=family_results, producer="test", generated_at=AS_OF)


def risk_family_result(family: StrategyFamily, *, verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW, reasons: tuple = ()) -> RiskFamilyResult:
    eligible = verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
    return RiskFamilyResult.model_construct(
        family=family,
        verdict=verdict,
        reasons=reasons,
        max_individual_risk=Decimal("100") if eligible else None,
        recommended_units=Decimal("1") if eligible else None,
    )


def risk_result(family_results: tuple[RiskFamilyResult, ...]) -> StrategyRiskResult:
    return StrategyRiskResult.model_construct(
        strategy_policy_result=None, trading_cycle_config=None, account_snapshot=None, candidate_inputs=(), outcome=None, family_results=family_results
    )


def portfolio_family_result(
    family: StrategyFamily, *, verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW, reasons: tuple = ()
) -> PortfolioFamilyResult:
    eligible = verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    return PortfolioFamilyResult.model_construct(
        family=family, verdict=verdict, reasons=reasons, portfolio_allocated_risk=Decimal("100") if eligible else None
    )


def portfolio_result(risk: StrategyRiskResult, family_results: tuple[PortfolioFamilyResult, ...]) -> StrategyPortfolioResult:
    return StrategyPortfolioResult.model_construct(strategy_risk_result=risk, outcome=None, family_results=family_results)


def session_family_result(
    family: StrategyFamily, *, verdict=SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW, reasons: tuple = ()
) -> SessionFamilyResult:
    eligible = verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW
    return SessionFamilyResult.model_construct(
        family=family, verdict=verdict, reasons=reasons, session_allocated_risk=Decimal("100") if eligible else None
    )


def session_result(portfolio: StrategyPortfolioResult, family_results: tuple[SessionFamilyResult, ...]) -> StrategySessionResult:
    return StrategySessionResult.model_construct(
        strategy_portfolio_result=portfolio, locked_override=False, session_status=None, outcome=None, family_results=family_results
    )


def final_recommendation(family: StrategyFamily, trade_id: str, *, symbol: str = SYMBOL) -> FinalRecommendation:
    return FinalRecommendation(
        trade_id=trade_id,
        family=family,
        symbol=symbol,
        direction=TradeDirection.LONG,
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0900"),
        take_profit_levels=(Decimal("1.1200"),),
        approved_volume=Decimal("0.50"),
        approved_risk_amount=Decimal("25.00"),
        account_currency="USD",
        signal_time=AS_OF,
        valid_until=VALID_UNTIL,
    )


def final_family_result(
    family: StrategyFamily,
    *,
    verdict=FinalRecommendationVerdict.ACTIONABLE,
    reasons: tuple = (),
    recommendation: FinalRecommendation | None = None,
    trade_id: str | None = None,
) -> FinalRecommendationFamilyResult:
    if verdict is FinalRecommendationVerdict.ACTIONABLE and recommendation is None:
        assert trade_id is not None
        recommendation = final_recommendation(family, trade_id)
    return FinalRecommendationFamilyResult.model_construct(
        family=family, verdict=verdict, reasons=reasons, sizing_result=None, recommendation=recommendation
    )


def final_construction_result(
    drp: DecisionRiskPipelineResult | None, family_results: tuple[FinalRecommendationFamilyResult, ...]
) -> FinalRecommendationConstructionResult:
    return FinalRecommendationConstructionResult.model_construct(decision_risk_pipeline_result=drp, outcome=None, family_results=family_results)


def decision_risk_pipeline_result(
    *, setup, event: HighImpactEventRiskResult | None, session: StrategySessionResult | None, outcome: DecisionRiskPipelineOutcome = DecisionRiskPipelineOutcome.COMPLETED
) -> DecisionRiskPipelineResult:
    return DecisionRiskPipelineResult.model_construct(
        outcome=outcome, strategy_setup_result=setup, account_risk_snapshot_assembly=None, strategy_session_result=session, high_impact_event_risk_result=event
    )


def netting_guard(outcome, *, symbol: str = SYMBOL, account_position_mode=AccountPositionMode.NETTING) -> NettingGuardResult:
    return NettingGuardResult(symbol=symbol, account_position_mode=account_position_mode, outcome=outcome)


def tracking_outcome(trade_id: str, outcome: MT5TrackedRecommendationCreationOutcome) -> TrackingIssuancePersistenceOutcome:
    return TrackingIssuancePersistenceOutcome(
        trade_id=trade_id,
        tracking_creation_outcome=outcome,
        tracking_persisted=outcome is MT5TrackedRecommendationCreationOutcome.CREATED,
        provenance_persisted=outcome is MT5TrackedRecommendationCreationOutcome.CREATED,
    )


def runtime_cycle_result(
    *,
    outcome,
    decision_risk_pipeline_result: DecisionRiskPipelineResult | None = None,
    final_recommendation_construction_result: FinalRecommendationConstructionResult | None = None,
    netting_guard_result: NettingGuardResult | None = None,
    new_tracking_persistence_outcomes: tuple[TrackingIssuancePersistenceOutcome, ...] = (),
    positions_read_status: str | None = "OK",
    history_read_status: str | None = "OK",
    mt5_state: MT5ConnectivityState = MT5ConnectivityState.AVAILABLE,
) -> RuntimeCycleResult:
    return RuntimeCycleResult.model_construct(
        as_of=AS_OF,
        outcome=outcome,
        mt5_runtime_status=MT5RuntimeStatus(as_of=AS_OF, state=mt5_state),
        account_facts=None,
        account_position_mode=None,
        positions_read_status=positions_read_status,
        history_read_status=history_read_status,
        target_symbol_facts_available=True,
        rollover_snapshot=None,
        rollover_persisted=None,
        realized_daily_pnl_assessment=None,
        open_risk_assessment=None,
        account_risk_snapshot_assembly=None,
        decision_risk_pipeline_result=decision_risk_pipeline_result,
        final_recommendation_construction_result=final_recommendation_construction_result,
        netting_guard_result=netting_guard_result,
        new_tracking_results=(),
        new_tracking_persistence_outcomes=new_tracking_persistence_outcomes,
        advanced_tracking=(),
        excluded_tracked_recommendations=(),
    )


def flow_health() -> FlowRealtimeBootstrapHealth:
    stream = StreamHealth(provider="fake", stream="market", status="CONNECTED", checked_at=AS_OF)
    task = TaskHealth(state=TaskState.RUNNING)
    return FlowRealtimeBootstrapHealth(
        market=stream,
        order_book=stream,
        open_interest_last_attempt_at=None,
        open_interest_last_success_at=None,
        market_transport_task=task,
        public_transport_task=task,
        trades_task=task,
        liquidations_task=task,
        order_book_task=task,
        funding_task=task,
        funding_cache_refresh_task=task,
        open_interest_task=task,
    )


def explanation_result(*, provider_status: ExplanationProviderStatus = ExplanationProviderStatus.LLM_UNAVAILABLE) -> ExplanationResult:
    return ExplanationResult(
        content_status=ExplanationContentStatus.AVAILABLE, provider_status=provider_status, headline="test headline", cycle_summary="test cycle summary"
    )


def production_advisory_cycle_result(
    *, rcr: RuntimeCycleResult, outcome: ProductionAdvisoryCycleOutcome = ProductionAdvisoryCycleOutcome.READY, llm_enabled: bool = False
) -> ProductionAdvisoryCycleResult:
    return ProductionAdvisoryCycleResult(
        as_of=AS_OF,
        symbol=SYMBOL,
        market_data_symbol=SYMBOL,
        outcome=outcome,
        runtime_cycle_result=rcr,
        explanation_result=explanation_result(),
        llm_enabled=llm_enabled,
        flow_health=flow_health(),
        technical_fetch_failures=(),
        cycle_duration_seconds=0.01,
    )


def not_eligible_family(family: StrategyFamily) -> StrategyEligibilityEntry:
    """A quick, deterministic "no trade" family for tests that need the
    other 3 ``StrategyFamily`` slots filled but not interesting - blocked at
    EVALUATION so no downstream container needs an entry for it at all."""
    from app.core.enums.strategy_router import StrategyIneligibilityReason

    return eligibility_entry(family, eligible=False, reasons=(StrategyIneligibilityReason.CONTOUR_MISSING,))


def full_actionable_pipeline(trade_ids: dict[StrategyFamily, str]) -> tuple[DecisionRiskPipelineResult, FinalRecommendationConstructionResult]:
    """Every ``StrategyFamily`` reaches ``FinalRecommendationVerdict.ACTIONABLE``
    - the "everything succeeds" baseline for issuance/status tests."""
    families = tuple(StrategyFamily)
    eligibility_entries = tuple(eligibility_entry(f) for f in families)
    router = router_result(eligibility_entries)
    judge = judge_result(router)
    policy_families = tuple(policy_family_result(f) for f in families)
    policy = policy_result(judge, policy_families)
    setup_families = tuple(setup_family_result(f) for f in families)
    setup = setup_result(policy, setup_families)
    event_families = tuple(event_family_result(f) for f in families)
    event = event_result(event_families)
    risk_families = tuple(risk_family_result(f) for f in families)
    risk = risk_result(risk_families)
    portfolio_families = tuple(portfolio_family_result(f) for f in families)
    portfolio = portfolio_result(risk, portfolio_families)
    session_families = tuple(session_family_result(f) for f in families)
    session = session_result(portfolio, session_families)
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session, outcome=DecisionRiskPipelineOutcome.COMPLETED)
    final_families = tuple(final_family_result(f, trade_id=trade_ids[f]) for f in families)
    frcr = final_construction_result(drp, final_families)
    return drp, frcr


def one_family_actionable_others_ineligible(
    actionable_family: StrategyFamily, trade_id: str
) -> tuple[DecisionRiskPipelineResult, FinalRecommendationConstructionResult]:
    """``actionable_family`` reaches ``ACTIONABLE``; every other family is
    blocked at EVALUATION (cheapest possible fixture for a single-family
    issuance/status scenario that still exercises the full 4-family
    ``StrategyFamily`` loop in ``map_recommendations``)."""
    other_families = [f for f in StrategyFamily if f is not actionable_family]
    eligibility_entries = (eligibility_entry(actionable_family),) + tuple(not_eligible_family(f) for f in other_families)
    router = router_result(eligibility_entries)
    judge = judge_result(router)
    policy_families = (policy_family_result(actionable_family),)
    policy = policy_result(judge, policy_families)
    setup_families = (setup_family_result(actionable_family),)
    setup = setup_result(policy, setup_families)
    event_families = (event_family_result(actionable_family),)
    event = event_result(event_families)
    risk_families = (risk_family_result(actionable_family),)
    risk = risk_result(risk_families)
    portfolio_families = (portfolio_family_result(actionable_family),)
    portfolio = portfolio_result(risk, portfolio_families)
    session_families = (session_family_result(actionable_family),)
    session = session_result(portfolio, session_families)
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session, outcome=DecisionRiskPipelineOutcome.COMPLETED)
    final_families = (final_family_result(actionable_family, trade_id=trade_id),)
    frcr = final_construction_result(drp, final_families)
    return drp, frcr


__all__ = [
    "AS_OF",
    "SYMBOL",
    "VALID_UNTIL",
    "decision_risk_pipeline_result",
    "default_setup",
    "eligibility_entry",
    "event_family_result",
    "event_result",
    "explanation_result",
    "FakeCycleReceiptPersistence",
    "final_construction_result",
    "final_family_result",
    "final_recommendation",
    "flow_health",
    "full_actionable_pipeline",
    "judge_result",
    "netting_guard",
    "not_eligible_family",
    "one_family_actionable_others_ineligible",
    "policy_family_result",
    "policy_result",
    "portfolio_family_result",
    "portfolio_result",
    "production_advisory_cycle_result",
    "risk_family_result",
    "risk_result",
    "router_result",
    "runtime_cycle_result",
    "session_family_result",
    "session_result",
    "setup_family_result",
    "setup_result",
    "tracking_outcome",
]
