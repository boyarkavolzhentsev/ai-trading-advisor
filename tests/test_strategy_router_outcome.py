"""Stage 6A ``StrategyRouterOutcome`` derivation - participation only, no
ranking, no preferred strategy, no winner."""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily, StrategyRouterOutcome
from app.strategies.router import StrategyRouter
from tests.market_evaluation_support import full_external_result, full_flow_result, full_technical_result, make_context
from tests.strategy_router_support import evaluation, external_result_matched


def test_zero_eligible_yields_no_eligible_strategy() -> None:
    result = StrategyRouter().route(market_evaluation=evaluation())
    assert result.outcome is StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY
    assert result.eligible_families == ()


def test_one_eligible_yields_routed() -> None:
    result = StrategyRouter().route(market_evaluation=evaluation(technical=full_technical_result()))
    assert result.outcome is StrategyRouterOutcome.ROUTED
    assert result.eligible_families == (StrategyFamily.TREND_FOLLOWING, StrategyFamily.MEAN_REVERSION)


def test_multiple_eligible_yields_routed() -> None:
    result = StrategyRouter().route(
        market_evaluation=evaluation(technical=full_technical_result(), flow=full_flow_result())
    )
    assert result.outcome is StrategyRouterOutcome.ROUTED
    assert result.eligible_families == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
    )


def test_all_four_eligible_yields_routed() -> None:
    result = StrategyRouter().route(
        market_evaluation=evaluation(
            technical=full_technical_result(),
            flow=full_flow_result(),
            external=external_result_matched(),
            context=make_context(),
        )
    )
    assert result.outcome is StrategyRouterOutcome.ROUTED
    assert result.eligible_families == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    )


def test_no_ranking_or_winner_field_exists() -> None:
    result = StrategyRouter().route(
        market_evaluation=evaluation(technical=full_technical_result(), flow=full_flow_result())
    )
    # outcome/eligible_families expose participation only - no ordering
    # claim beyond the fixed StrategyFamily declaration order is implied.
    assert set(StrategyRouterOutcome) == {StrategyRouterOutcome.ROUTED, StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY}
    assert not hasattr(result, "preferred_family")
    assert not hasattr(result, "winner")
    assert not hasattr(result, "best_family")
