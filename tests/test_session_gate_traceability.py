"""Stage 9: the full upstream chain remains reachable through the embedded
``StrategyPortfolioResult`` - never copied out onto ``StrategySessionResult``
itself."""

from __future__ import annotations

from tests.session_support import route_to_portfolio_and_session


def test_full_upstream_chain_reachable() -> None:
    portfolio_result, session_result = route_to_portfolio_and_session()

    assert session_result.strategy_portfolio_result is portfolio_result
    strategy_risk_result = session_result.strategy_portfolio_result.strategy_risk_result
    strategy_policy_result = strategy_risk_result.strategy_policy_result
    strategy_judge_result = strategy_policy_result.strategy_judge_result
    strategy_router_result = strategy_judge_result.strategy_router_result
    market_evaluation_result = strategy_router_result.market_evaluation

    assert strategy_risk_result.account_snapshot is not None
    assert strategy_risk_result.trading_cycle_config is not None
    assert market_evaluation_result is not None


def test_session_result_carries_no_duplicated_upstream_payload() -> None:
    """StrategySessionResult's own field set carries no evidence/direction/
    account-snapshot copy - only the embedded result, the one new
    locked_override fact, and Stage 9's own derived fields."""
    _, session_result = route_to_portfolio_and_session()
    top_level_fields = set(type(session_result).model_fields)
    assert top_level_fields == {"strategy_portfolio_result", "locked_override", "session_status", "outcome", "family_results"}
