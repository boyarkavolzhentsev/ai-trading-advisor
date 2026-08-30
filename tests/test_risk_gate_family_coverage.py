"""Stage 7 family coverage: RiskGate evaluates exactly one ``RiskFamilyResult``
per ``PolicyFamilyResult``, in the same canonical order."""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.policy_gate_support import route_judge_and_gate
from tests.risk_gate_support import default_account_snapshot, default_candidates_for, default_config
from app.risk.engine import RiskGate
from tests.strategy_judge_support import external_with_news_sentiment


def test_family_results_match_policy_family_results_one_to_one() -> None:
    _, _, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    policy_families = tuple(r.family for r in policy_result.family_results)
    risk_families = tuple(r.family for r in risk_result.family_results)
    assert risk_families == policy_families
    assert len(risk_result.family_results) == len(policy_result.family_results)


def test_canonical_family_order_preserved() -> None:
    _, _, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    assert tuple(r.family for r in policy_result.family_results) == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    )
    assert tuple(r.family for r in risk_result.family_results) == tuple(r.family for r in policy_result.family_results)
