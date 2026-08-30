"""Stage 6C family coverage: PolicyGate evaluates exactly one
``PolicyFamilyResult`` per ``JudgeFamilyResult``, in the same canonical order,
no duplicate/missing/extra family."""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.policy_gate_support import route_judge_and_gate
from tests.strategy_judge_support import external_with_news_sentiment


def test_no_eligible_families_yields_no_policy_results() -> None:
    _, judge_result, policy_result = route_judge_and_gate()
    assert judge_result.family_results == ()
    assert policy_result.family_results == ()


def test_family_results_match_judge_family_results_one_to_one() -> None:
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    judge_families = tuple(result.family for result in judge_result.family_results)
    policy_families = tuple(result.family for result in policy_result.family_results)
    assert policy_families == judge_families
    assert len(policy_result.family_results) == len(judge_result.family_results)


def test_canonical_family_order_preserved() -> None:
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    assert tuple(result.family for result in judge_result.family_results) == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    )
    assert tuple(result.family for result in policy_result.family_results) == tuple(
        result.family for result in judge_result.family_results
    )


def test_no_duplicate_families() -> None:
    _, _, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    families = [result.family for result in policy_result.family_results]
    assert len(set(families)) == len(families)


def test_technical_only_never_produces_breakout_or_event_driven() -> None:
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    families = {result.family for result in policy_result.family_results}
    assert StrategyFamily.BREAKOUT not in families
    assert StrategyFamily.EVENT_DRIVEN not in families
