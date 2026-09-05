"""Final Recommendation behavioral tests (Final Runtime Integration, Part D).

Builds real ``DecisionRiskPipelineResult`` fixtures via the real Decision/Risk
Pipeline, then runs them through the real ``construct_final_recommendations``
- never a hand-rolled result - asserting against the exact same downstream
Stage 10C contract its own test suite already verifies independently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.final_recommendation import FinalRecommendationBlockReason, FinalRecommendationOutcome, FinalRecommendationVerdict
from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.orchestration.final_recommendation import construct_final_recommendations
from tests.final_recommendation_support import (
    NOW,
    actionable_trend_market_structure,
    blocked_assembly,
    opposite_direction_market_structure,
    opposite_direction_technical,
    run_pipeline,
    symbol_facts,
    trend_following_technical,
)
from tests.market_evaluation_support import full_flow_result
from tests.strategy_judge_support import technical_with_trend_observations


def _result_for(construction_result, family):
    return next(r for r in construction_result.family_results if r.family is family)


# --- A/one actionable family ---


def test_one_actionable_family() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )

    assert result.outcome is FinalRecommendationOutcome.SOME_ACTIONABLE
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.ACTIONABLE
    assert trend.recommendation is not None
    assert trend.recommendation.direction is TradeDirection.LONG


# --- B/C: multiple + opposite-direction actionable families ---


def test_multiple_opposite_direction_actionable_families_coexist() -> None:
    pipeline_result = run_pipeline(
        technical=opposite_direction_technical(),
        flow=full_flow_result(),
        m15_market_structure=opposite_direction_market_structure(),
    )
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-long", StrategyFamily.BREAKOUT: "trade-short"},
        as_of=NOW,
    )

    assert result.outcome is FinalRecommendationOutcome.SOME_ACTIONABLE
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    breakout = _result_for(result, StrategyFamily.BREAKOUT)
    assert trend.verdict is FinalRecommendationVerdict.ACTIONABLE
    assert breakout.verdict is FinalRecommendationVerdict.ACTIONABLE
    assert trend.recommendation.direction is TradeDirection.LONG
    assert breakout.recommendation.direction is TradeDirection.SHORT
    assert trend.recommendation.trade_id == "trade-long"
    assert breakout.recommendation.trade_id == "trade-short"


# --- D: zero actionable families ---


def test_zero_actionable_families() -> None:
    """No technical/flow/external at all: Router finds nothing eligible, so
    Stage 9 (and therefore this stage) legitimately produces zero family
    entries - never a fabricated ``SESSION_NOT_ELIGIBLE`` entry per family."""
    pipeline_result = run_pipeline(technical=None, m15_market_structure=None)
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    assert result.outcome is FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
    assert result.family_results == ()


def test_zero_actionable_families_with_session_blocked_families_present() -> None:
    """Router-eligible but Judge-``INSUFFICIENT_EVIDENCE`` families reach
    Stage 9 as ``BLOCKED_BY_SESSION`` - this stage must report each one as
    ``SESSION_NOT_ELIGIBLE``, never invoking Stage 10C for any of them."""
    pipeline_result = run_pipeline(
        technical=technical_with_trend_observations(return_direction=None, slope_direction=None),
        m15_market_structure=actionable_trend_market_structure(),
    )
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    assert result.outcome is FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
    assert result.family_results
    assert all(r.verdict is FinalRecommendationVerdict.BLOCKED for r in result.family_results)
    assert all(r.reasons == (FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE,) for r in result.family_results)
    assert all(r.sizing_result is None for r in result.family_results)


# --- E: pipeline BLOCKED_BEFORE_RISK short-circuits Stage 10C ---


def test_pipeline_blocked_before_risk_short_circuits() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(),
        m15_market_structure=actionable_trend_market_structure(),
        account_risk_snapshot_assembly=blocked_assembly(),
    )
    assert pipeline_result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK

    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    assert result.outcome is FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK
    assert result.family_results == ()
    assert result.decision_risk_pipeline_result is pipeline_result


# --- F/G: explicit StrategyFamily join, tuple-reorder safety ---


def test_family_join_is_by_strategy_family_not_tuple_position() -> None:
    """Reordering ``StrategySetupResult.family_results`` before construction
    must not change which setup a family's recommendation is built from -
    proving the join is by explicit ``StrategyFamily`` key, never index."""
    pipeline_result = run_pipeline(
        technical=opposite_direction_technical(),
        flow=full_flow_result(),
        m15_market_structure=opposite_direction_market_structure(),
    )
    reordered_setup_result = pipeline_result.strategy_setup_result.model_copy(
        update={"family_results": tuple(reversed(pipeline_result.strategy_setup_result.family_results))}
    )
    reordered_pipeline_result = pipeline_result.model_copy(update={"strategy_setup_result": reordered_setup_result})

    baseline = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-long", StrategyFamily.BREAKOUT: "trade-short"},
        as_of=NOW,
    )
    reordered = construct_final_recommendations(
        decision_risk_pipeline_result=reordered_pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-long", StrategyFamily.BREAKOUT: "trade-short"},
        as_of=NOW,
    )

    baseline_trend = _result_for(baseline, StrategyFamily.TREND_FOLLOWING)
    reordered_trend = _result_for(reordered, StrategyFamily.TREND_FOLLOWING)
    assert baseline_trend.recommendation.direction is TradeDirection.LONG
    assert reordered_trend.recommendation.direction is TradeDirection.LONG
    assert baseline_trend.recommendation.entry_price == reordered_trend.recommendation.entry_price
    assert baseline_trend.recommendation.stop_loss == reordered_trend.recommendation.stop_loss


# --- H/I/J/K/L: exact field passthrough into and out of Stage 10C ---


def test_exact_setup_and_session_facts_passed_unchanged_into_stage_10c() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    setup = next(
        r.setup for r in pipeline_result.strategy_setup_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )
    session = next(
        r for r in pipeline_result.strategy_session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )

    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)

    assert trend.sizing_result.outcome is MT5SizingOutcome.ACTIONABLE
    assert trend.recommendation.entry_price == setup.entry_price
    assert trend.recommendation.stop_loss == setup.stop_loss
    assert trend.recommendation.approved_volume == trend.sizing_result.broker_volume
    assert trend.recommendation.approved_risk_amount == trend.sizing_result.actual_monetary_risk
    # actual_monetary_risk must come from Stage 10C, never substituted with session_allocated_risk:
    assert trend.recommendation.approved_risk_amount == trend.sizing_result.actual_monetary_risk
    assert session.session_allocated_risk is not None


# --- M: non-ACTIONABLE Stage 10C blocks recommendation ---


def test_non_actionable_stage_10c_blocks_recommendation() -> None:
    """A far stop (as in Part C's own fixtures) produces a broker volume
    below the minimum - Stage 10C's own ``BELOW_BROKER_MINIMUM_VOLUME``,
    preserved unchanged, never reinterpreted."""
    from tests.decision_risk_pipeline_support import trend_following_market_structure as far_market_structure

    pipeline_result = run_pipeline(technical=trend_following_technical(), m15_market_structure=far_market_structure())
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.BLOCKED
    assert trend.reasons == (FinalRecommendationBlockReason.SIZING_NOT_ACTIONABLE,)
    assert trend.sizing_result is not None
    assert trend.sizing_result.outcome is MT5SizingOutcome.BELOW_BROKER_MINIMUM_VOLUME
    assert trend.recommendation is None


# --- N: symbol mismatch fails closed before sizing ---


def test_symbol_mismatch_fails_closed_before_sizing() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    mismatched_symbol_facts = symbol_facts(symbol="ETHUSDT")

    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=mismatched_symbol_facts,
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.BLOCKED
    assert trend.reasons == (FinalRecommendationBlockReason.SYMBOL_FACTS_MISMATCH,)
    assert trend.sizing_result is None
    assert trend.recommendation is None


# --- O/P: expiry ---


def test_expired_setup_fails_closed() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    setup = next(
        r.setup for r in pipeline_result.strategy_setup_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )
    after_expiry = setup.valid_until + timedelta(seconds=1)

    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=after_expiry,
    )
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.BLOCKED
    assert trend.reasons == (FinalRecommendationBlockReason.SETUP_EXPIRED,)
    assert trend.sizing_result is None


def test_as_of_equal_to_valid_until_remains_valid() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    setup = next(
        r.setup for r in pipeline_result.strategy_setup_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )

    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=setup.valid_until,
    )
    trend = _result_for(result, StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.ACTIONABLE


# --- Z: determinism ---


def test_determinism_same_inputs_produce_equal_outputs() -> None:
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    kwargs = dict(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    first = construct_final_recommendations(**kwargs)
    second = construct_final_recommendations(**kwargs)
    assert first == second
