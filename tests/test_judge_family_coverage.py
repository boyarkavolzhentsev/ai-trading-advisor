"""Stage 6B family coverage: Judge evaluates only Router-eligible families,
in canonical order, one result each."""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge


def test_no_eligible_families_yields_no_judge_results() -> None:
    _, judge_result = route_and_judge()
    assert judge_result.family_results == ()


def test_router_ineligible_family_never_judged() -> None:
    """Technical-only evaluation: BREAKOUT and EVENT_DRIVEN stay ineligible
    at Router and must never appear in family_results."""
    router_result, judge_result = route_and_judge(technical=full_technical_result())
    assert router_result.eligible_families == (StrategyFamily.TREND_FOLLOWING, StrategyFamily.MEAN_REVERSION)
    judged_families = {result.family for result in judge_result.family_results}
    assert judged_families == {StrategyFamily.TREND_FOLLOWING, StrategyFamily.MEAN_REVERSION}
    assert StrategyFamily.BREAKOUT not in judged_families
    assert StrategyFamily.EVENT_DRIVEN not in judged_families


def test_canonical_family_order_preserved() -> None:
    router_result, judge_result = route_and_judge(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    assert router_result.eligible_families == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    )
    assert tuple(result.family for result in judge_result.family_results) == router_result.eligible_families


def test_multiple_eligible_families_judged_independently() -> None:
    """All four eligible; each family_result reflects only its own rule -
    no cross-family influence."""
    _, judge_result = route_and_judge(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
    )
    outcomes = {result.family: result for result in judge_result.family_results}
    # MEAN_REVERSION is always insufficient regardless of any other family's outcome.
    assert outcomes[StrategyFamily.MEAN_REVERSION].outcome.value == "INSUFFICIENT_EVIDENCE"
    # EVENT_DRIVEN's own negative-sentiment result must not leak into TREND_FOLLOWING/BREAKOUT.
    for family in (StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT):
        for ref in outcomes[family].evidence_refs:
            assert ref.contour.value != "EXTERNAL"
