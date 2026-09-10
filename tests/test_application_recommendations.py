"""Recommendation-authority tests: ``RecommendationDTO`` is sourced only
from ``FinalRecommendation``, and only a genuinely-issued (Part E
tracking-CREATED) ``ACTIONABLE`` family is ever exposed as a recommendation -
never reconstructed from the NETTING/HEDGING rule directly."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.advisory_service import is_issuable, map_recommendations
from app.application.dto import NoTradeStage
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_runtime import AccountPositionMode
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from tests.application_support import (
    full_actionable_pipeline,
    netting_guard,
    one_family_actionable_others_ineligible,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)


def _trade_ids() -> dict[StrategyFamily, str]:
    return {f: f"TID__{f.value}" for f in StrategyFamily}


# --- authoritative field sourcing -------------------------------------------


def test_recommendation_preserves_decimal_and_facts() -> None:
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
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade = map_recommendations(cycle)

    assert len(recommendations) == 1
    rec = recommendations[0]
    assert isinstance(rec.entry_price, Decimal)
    assert isinstance(rec.approved_volume, Decimal)
    assert isinstance(rec.approved_risk_amount, Decimal)
    assert rec.account_currency == "USD"
    assert rec.signal_time is not None
    assert rec.valid_until is not None
    assert rec.trade_id == trade_id
    assert rec.strategy_family is family
    assert no_trade  # the 3 other, ineligible families each get a no_trade reason


def test_narrative_disagreement_cannot_alter_recommendation_facts() -> None:
    """RecommendationDTO is built purely from FinalRecommendation - the
    mapping function has no code path that could read ExplanationResult at
    all (see test_application_no_trade.py's own module-import assertion);
    this test additionally proves the produced DTO's fields exactly match
    the source FinalRecommendation regardless of whatever narrative content
    a cycle happens to carry."""
    family = StrategyFamily.EVENT_DRIVEN
    trade_id = "cyc__EVENT_DRIVEN"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    source_recommendation = frcr.family_results[0].recommendation
    recommendations, _ = map_recommendations(cycle)
    rec = recommendations[0]
    assert rec.direction == source_recommendation.direction
    assert rec.entry_price == source_recommendation.entry_price
    assert rec.stop_loss == source_recommendation.stop_loss


# --- NETTING ----------------------------------------------------------------


def test_netting_allowed_single_actionable_exposed() -> None:
    family = StrategyFamily.TREND_FOLLOWING
    trade_id = "cyc__TREND_FOLLOWING"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED, account_position_mode=AccountPositionMode.NETTING),
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade = map_recommendations(cycle)
    assert len(recommendations) == 1
    assert recommendations[0].trade_id == trade_id


def test_netting_blocked_multiple_actionable_not_exposed() -> None:
    trade_ids = _trade_ids()
    drp, frcr = full_actionable_pipeline(trade_ids)
    # netting guard suppressed the whole cycle - construct_tracked_recommendations
    # was never called, so new_tracking_persistence_outcomes is empty.
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS, account_position_mode=AccountPositionMode.NETTING),
        new_tracking_persistence_outcomes=(),
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert recommendations == ()
    assert len(no_trade_reasons) == 4
    for reason in no_trade_reasons:
        assert reason.stage is NoTradeStage.ISSUANCE
        assert reason.codes == (NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS,)


def test_netting_blocked_existing_position_not_exposed() -> None:
    family = StrategyFamily.MEAN_REVERSION
    trade_id = "cyc__MEAN_REVERSION"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION, account_position_mode=AccountPositionMode.NETTING),
        new_tracking_persistence_outcomes=(),
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert recommendations == ()
    assert any(r.stage is NoTradeStage.ISSUANCE and r.codes == (NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION,) for r in no_trade_reasons)


# --- UNKNOWN -----------------------------------------------------------------


def test_unknown_mode_mirrors_netting_suppression_semantics() -> None:
    trade_ids = _trade_ids()
    drp, frcr = full_actionable_pipeline(trade_ids)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS, account_position_mode=AccountPositionMode.UNKNOWN),
        new_tracking_persistence_outcomes=(),
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert recommendations == ()
    assert len(no_trade_reasons) == 4


# --- HEDGING -----------------------------------------------------------------


def test_hedging_multiple_created_recommendations_all_exposed() -> None:
    trade_ids = _trade_ids()
    drp, frcr = full_actionable_pipeline(trade_ids)
    tracking = tuple(tracking_outcome(tid, MT5TrackedRecommendationCreationOutcome.CREATED) for tid in trade_ids.values())
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=None,  # never evaluated under HEDGING
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert len(recommendations) == 4
    assert no_trade_reasons == ()
    assert {r.trade_id for r in recommendations} == set(trade_ids.values())


def test_hedging_snapshot_unavailable_for_one_family_not_exposed() -> None:
    trade_ids = _trade_ids()
    drp, frcr = full_actionable_pipeline(trade_ids)
    families = list(StrategyFamily)
    failing_family = families[0]
    tracking = tuple(
        tracking_outcome(
            trade_ids[f],
            MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE if f is failing_family else MT5TrackedRecommendationCreationOutcome.CREATED,
        )
        for f in families
    )
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=None,
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    recommendations, no_trade_reasons = map_recommendations(cycle)
    assert len(recommendations) == 3
    assert failing_family not in {r.strategy_family for r in recommendations}
    matching = [r for r in no_trade_reasons if r.strategy_family is failing_family]
    assert len(matching) == 1
    assert matching[0].stage is NoTradeStage.ISSUANCE
    assert matching[0].codes == (MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE,)


# --- is_issuable direct unit tests ------------------------------------------


def test_is_issuable_true_only_for_created_outcome() -> None:
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        new_tracking_persistence_outcomes=(tracking_outcome("abc", MT5TrackedRecommendationCreationOutcome.CREATED),),
    )
    assert is_issuable("abc", rcr) is True
    assert is_issuable("other", rcr) is False


def test_is_issuable_false_for_snapshot_unavailable() -> None:
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        new_tracking_persistence_outcomes=(tracking_outcome("abc", MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE),),
    )
    assert is_issuable("abc", rcr) is False
