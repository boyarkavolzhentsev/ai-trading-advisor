"""``FinalRecommendationConstructionResult``/``FinalRecommendationFamilyResult``
invariants: every valid/invalid outcome vs. family_results combination.

Reuses real results produced by the real ``construct_final_recommendations``
as a source of genuinely valid embedded fields, then recombines those fields
into the invalid combinations the models must reject.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.final_recommendation import FinalRecommendationOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.final_recommendation import FinalRecommendationConstructionResult
from app.orchestration.final_recommendation import construct_final_recommendations
from tests.decision_risk_pipeline_support import trend_following_market_structure as far_market_structure
from tests.final_recommendation_support import (
    NOW,
    actionable_trend_market_structure,
    blocked_assembly,
    run_pipeline,
    symbol_facts,
    trend_following_technical,
)


def _actionable_result():
    pipeline_result = run_pipeline(technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure())
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )


def _no_actionable_result():
    pipeline_result = run_pipeline(technical=trend_following_technical(), m15_market_structure=far_market_structure())
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )


def _pipeline_blocked_result():
    pipeline_result = run_pipeline(
        technical=trend_following_technical(),
        m15_market_structure=actionable_trend_market_structure(),
        account_risk_snapshot_assembly=blocked_assembly(),
    )
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )


def test_some_actionable_constructs() -> None:
    result = _actionable_result()
    assert result.outcome is FinalRecommendationOutcome.SOME_ACTIONABLE


def test_no_actionable_family_constructs() -> None:
    result = _no_actionable_result()
    assert result.outcome is FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY


def test_pipeline_blocked_before_risk_constructs() -> None:
    result = _pipeline_blocked_result()
    assert result.outcome is FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK
    assert result.family_results == ()


def test_pipeline_blocked_before_risk_must_not_carry_family_results() -> None:
    actionable = _actionable_result()
    blocked = _pipeline_blocked_result()
    with pytest.raises(ValidationError):
        FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=blocked.decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK,
            family_results=actionable.family_results,
        )


def test_completed_pipeline_must_not_use_pipeline_blocked_outcome() -> None:
    actionable = _actionable_result()
    with pytest.raises(ValidationError):
        FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=actionable.decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK,
            family_results=(),
        )


def test_blocked_pipeline_must_not_use_completed_outcome() -> None:
    actionable = _actionable_result()
    blocked = _pipeline_blocked_result()
    with pytest.raises(ValidationError):
        FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=blocked.decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.SOME_ACTIONABLE,
            family_results=actionable.family_results,
        )


def test_outcome_must_match_per_family_derivation() -> None:
    no_actionable = _no_actionable_result()
    with pytest.raises(ValidationError):
        FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=no_actionable.decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.SOME_ACTIONABLE,
            family_results=no_actionable.family_results,
        )


def test_family_results_must_match_session_family_results_families() -> None:
    """``no_actionable``/``actionable`` share the identical routed family set
    (both from ``trend_following_technical()``), so a genuinely different
    family set - the fully-empty no-market-data case - is used to prove the
    coverage validator actually fires."""
    actionable = _actionable_result()
    empty = construct_final_recommendations(
        decision_risk_pipeline_result=run_pipeline(technical=None, m15_market_structure=None),
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    assert empty.family_results == ()
    with pytest.raises(ValidationError):
        FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=empty.decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.SOME_ACTIONABLE,
            family_results=actionable.family_results,
        )
