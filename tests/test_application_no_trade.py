"""``derive_no_trade_reason`` precedence tests: one genuine root cause per
family, at the first pipeline stage it genuinely occurred - never inferred
from ``ExplanationResult``/narrative text, never a mirrored upstream reason
mistaken for a new one."""

from __future__ import annotations

from app.application.advisory_service import derive_no_trade_reason
from app.application.dto import NoTradeStage
from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.final_recommendation import FinalRecommendationBlockReason
from app.core.enums.high_impact_event import HighImpactEventBlockReason, HighImpactEventVerdict
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict
from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict
from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason
from tests.application_support import (
    AS_OF,
    decision_risk_pipeline_result,
    eligibility_entry,
    event_family_result,
    event_result,
    final_construction_result,
    final_family_result,
    judge_result,
    policy_family_result,
    policy_result,
    portfolio_family_result,
    portfolio_result,
    risk_family_result,
    risk_result,
    router_result,
    runtime_cycle_result,
    session_family_result,
    session_result,
    setup_family_result,
    setup_result,
)

FAMILY = StrategyFamily.MEAN_REVERSION


def _rcr(drp, final_construction=None):
    return runtime_cycle_result(outcome=RuntimeCycleOutcome.READY, decision_risk_pipeline_result=drp, final_recommendation_construction_result=final_construction)


# --- EVALUATION ----------------------------------------------------------


def test_evaluation_block_reported() -> None:
    router = router_result((eligibility_entry(FAMILY, eligible=False, reasons=(StrategyIneligibilityReason.CONTOUR_MISSING,)),))
    judge = judge_result(router)
    pol = policy_result(judge, ())
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason is not None
    assert reason.stage is NoTradeStage.EVALUATION
    assert reason.codes == (StrategyIneligibilityReason.CONTOUR_MISSING,)


def test_evaluation_multiple_reasons_preserved_in_order() -> None:
    reasons = (StrategyIneligibilityReason.CONTOUR_MISSING, StrategyIneligibilityReason.QUALITY_UNAVAILABLE)
    router = router_result((eligibility_entry(FAMILY, eligible=False, reasons=reasons),))
    judge = judge_result(router)
    pol = policy_result(judge, ())
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.codes == reasons


# --- JUDGE vs POLICY -------------------------------------------------------


def test_judge_outcome_mixed_maps_to_judge_stage() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY, verdict=PolicyFamilyVerdict.BLOCKED, reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED,)),))
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.JUDGE
    assert reason.codes == (PolicyBlockReason.JUDGE_OUTCOME_MIXED,)


def test_judge_outcome_insufficient_evidence_maps_to_judge_stage() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY, verdict=PolicyFamilyVerdict.BLOCKED, reasons=(PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE,)),))
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.JUDGE


def test_disallowed_evidence_quality_maps_to_policy_stage() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY, verdict=PolicyFamilyVerdict.BLOCKED, reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,)),))
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.POLICY
    assert reason.codes == (PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,)


# --- SETUP -----------------------------------------------------------------


def test_setup_block_reported() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup_families = (setup_family_result(FAMILY, outcome=SetupConstructionOutcome.BLOCKED, reasons=(SetupBlockReason.MISSING_STOP_REFERENCE,)),)
    setup = setup_result(pol, setup_families)
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.SETUP
    assert reason.codes == (SetupBlockReason.MISSING_STOP_REFERENCE,)


def test_setup_block_wins_over_zero_or_negative_risk_per_unit_sentinel() -> None:
    """Even if a RiskFamilyResult carrying ZERO_OR_NEGATIVE_RISK_PER_UNIT
    were present (the Decimal('0') sentinel effect), SETUP must win - the
    walk returns before Risk is ever consulted."""
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup_families = (setup_family_result(FAMILY, outcome=SetupConstructionOutcome.BLOCKED, reasons=(SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)),)
    setup = setup_result(pol, setup_families)
    risk = risk_result((risk_family_result(FAMILY, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=(RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT,)),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,)),))
    session = session_result(portfolio, (session_family_result(FAMILY, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)),))
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=session)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.SETUP
    assert reason.codes == (SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)


# --- EVENT -------------------------------------------------------------


def test_event_block_reported() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup_families = (setup_family_result(FAMILY),)
    setup = setup_result(pol, setup_families)
    event = event_result((event_family_result(FAMILY, verdict=HighImpactEventVerdict.BLOCKED, reasons=(HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,), next_safe_time=AS_OF),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=None)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.EVENT
    assert reason.codes == (HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,)


def test_event_block_wins_over_zero_or_negative_risk_per_unit_sentinel() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY, verdict=HighImpactEventVerdict.BLOCKED, reasons=(HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,), next_safe_time=AS_OF),))
    risk = risk_result((risk_family_result(FAMILY, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=(RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT,)),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,)),))
    session = session_result(portfolio, (session_family_result(FAMILY, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.EVENT


# --- RISK / PORTFOLIO / SESSION / FINAL precedence -------------------------


def test_risk_genuine_reason_wins_over_portfolio_risk_not_eligible() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY),))
    risk = risk_result((risk_family_result(FAMILY, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED,)),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,)),))
    session = session_result(portfolio, (session_family_result(FAMILY, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.RISK
    assert reason.codes == (RiskBlockReason.DAILY_LOSS_LIMIT_REACHED,)


def test_portfolio_genuine_reason_wins_over_session_portfolio_not_eligible() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY),))
    risk = risk_result((risk_family_result(FAMILY),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY, verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO, reasons=(PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,)),))
    session = session_result(portfolio, (session_family_result(FAMILY, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason.stage is NoTradeStage.PORTFOLIO
    assert reason.codes == (PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,)


def test_session_genuine_reason_wins_over_final_session_not_eligible() -> None:
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY),))
    risk = risk_result((risk_family_result(FAMILY),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY),))
    session = session_result(portfolio, (session_family_result(FAMILY, verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION, reasons=(SessionBlockReason.SESSION_LOCKED,)),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    final_construction = final_construction_result(drp, (final_family_result(FAMILY, verdict=__import__("app.core.enums.final_recommendation", fromlist=["FinalRecommendationVerdict"]).FinalRecommendationVerdict.BLOCKED, reasons=(FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE,)),))
    reason = derive_no_trade_reason(FAMILY, _rcr(drp, final_construction))
    assert reason.stage is NoTradeStage.SESSION
    assert reason.codes == (SessionBlockReason.SESSION_LOCKED,)


def test_final_genuine_reason_reported_when_no_earlier_block() -> None:
    from app.core.enums.final_recommendation import FinalRecommendationVerdict

    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY),))
    risk = risk_result((risk_family_result(FAMILY),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY),))
    session = session_result(portfolio, (session_family_result(FAMILY),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    final_construction = final_construction_result(
        drp, (final_family_result(FAMILY, verdict=FinalRecommendationVerdict.BLOCKED, reasons=(FinalRecommendationBlockReason.SIZING_NOT_ACTIONABLE,)),)
    )
    reason = derive_no_trade_reason(FAMILY, _rcr(drp, final_construction))
    assert reason.stage is NoTradeStage.FINAL
    assert reason.codes == (FinalRecommendationBlockReason.SIZING_NOT_ACTIONABLE,)


# --- no reason yet (still ACTIONABLE) --------------------------------------


def test_actionable_family_yields_no_no_trade_reason() -> None:
    from app.core.enums.final_recommendation import FinalRecommendationVerdict

    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    event = event_result((event_family_result(FAMILY),))
    risk = risk_result((risk_family_result(FAMILY),))
    portfolio = portfolio_result(risk, (portfolio_family_result(FAMILY),))
    session = session_result(portfolio, (session_family_result(FAMILY),))
    drp = decision_risk_pipeline_result(setup=setup, event=event, session=session)
    final_construction = final_construction_result(drp, (final_family_result(FAMILY, verdict=FinalRecommendationVerdict.ACTIONABLE, trade_id="TID"),))
    reason = derive_no_trade_reason(FAMILY, _rcr(drp, final_construction))
    assert reason is None


def test_blocked_before_risk_yields_no_per_family_reason() -> None:
    """Runtime Fact Assembly not READY - a whole-cycle fact, never invented
    as a per-family typed reason (see the approved corrective design
    closure's own documented gap)."""
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None, outcome=DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK)
    reason = derive_no_trade_reason(FAMILY, _rcr(drp))
    assert reason is None


def test_service_unavailable_yields_no_per_family_reason() -> None:
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.BLOCKED, decision_risk_pipeline_result=None)
    reason = derive_no_trade_reason(FAMILY, rcr)
    assert reason is None


# --- no narrative/text consulted -------------------------------------------


def test_derive_no_trade_reason_never_imports_explanation_models() -> None:
    import ast
    import inspect

    import app.application.advisory_service as service_module

    tree = ast.parse(inspect.getsource(service_module))
    imported_modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "app.core.models.explanation" not in imported_modules


# --- deterministic ordering -------------------------------------------------


def test_repeated_calls_produce_identical_result() -> None:
    router = router_result((eligibility_entry(FAMILY, eligible=False, reasons=(StrategyIneligibilityReason.CONTOUR_MISSING, StrategyIneligibilityReason.QUALITY_UNAVAILABLE)),))
    judge = judge_result(router)
    pol = policy_result(judge, ())
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    rcr = _rcr(drp)
    first = derive_no_trade_reason(FAMILY, rcr)
    second = derive_no_trade_reason(FAMILY, rcr)
    assert first == second
