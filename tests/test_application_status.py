"""``ApplicationAdvisoryStatus`` precedence tests: SERVICE_UNAVAILABLE >
DEGRADED > READY > NO_TRADE, with recommendations and status computed as
independent facts (a DEGRADED cycle may still carry recommendations)."""

from __future__ import annotations

from app.application.advisory_service import derive_application_status, map_recommendations
from app.application.dto import ApplicationAdvisoryStatus
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.application_support import (
    netting_guard,
    one_family_actionable_others_ineligible,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)


def test_service_unavailable_status() -> None:
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.BLOCKED)
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE)
    status = derive_application_status(cycle, ())
    assert status is ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE


def test_partial_degraded_with_recommendation_stays_degraded() -> None:
    family = StrategyFamily.TREND_FOLLOWING
    trade_id = "cyc__TREND_FOLLOWING"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    recommendations, _ = map_recommendations(cycle)
    assert len(recommendations) == 1  # recommendation retained despite DEGRADED
    status = derive_application_status(cycle, recommendations)
    assert status is ApplicationAdvisoryStatus.DEGRADED


def test_ready_with_recommendation_is_ready() -> None:
    family = StrategyFamily.BREAKOUT
    trade_id = "cyc__BREAKOUT"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    recommendations, _ = map_recommendations(cycle)
    status = derive_application_status(cycle, recommendations)
    assert status is ApplicationAdvisoryStatus.READY


def test_ready_with_no_recommendation_is_no_trade() -> None:
    from app.core.enums.strategy_router import StrategyIneligibilityReason
    from tests.application_support import (
        decision_risk_pipeline_result,
        eligibility_entry,
        final_construction_result,
        judge_result,
        policy_result,
        router_result,
        setup_result,
    )

    entries = tuple(eligibility_entry(f, eligible=False, reasons=(StrategyIneligibilityReason.CONTOUR_MISSING,)) for f in StrategyFamily)
    router = router_result(entries)
    judge = judge_result(router)
    pol = policy_result(judge, ())
    setup = setup_result(pol, ())
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    frcr = final_construction_result(drp, ())
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.READY, decision_risk_pipeline_result=drp, final_recommendation_construction_result=frcr)
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert recommendations == ()
    assert len(no_trade_reasons) == 4
    status = derive_application_status(cycle, recommendations)
    assert status is ApplicationAdvisoryStatus.NO_TRADE
