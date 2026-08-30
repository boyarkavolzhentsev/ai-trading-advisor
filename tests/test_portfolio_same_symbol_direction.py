"""Stage 8: same-symbol same-direction and same-symbol opposite-direction
families are treated identically - both count fully toward the shared
capacity, with no netting or offsetting."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.policy_gate_support import route_judge_and_gate
from tests.portfolio_support import route_judge_gate_risk_and_portfolio
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment


def test_same_symbol_same_direction_both_count_fully() -> None:
    """TREND_FOLLOWING and EVENT_DRIVEN both LONG_CANDIDATE, same symbol
    (all families in one evaluation share one symbol) - both count fully
    toward total_requested, no consolidation."""
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    directions = {r.family: r.direction for r in judge_result.family_results}
    assert directions[StrategyFamily.TREND_FOLLOWING] == directions[StrategyFamily.EVENT_DRIVEN]

    snapshot = default_account_snapshot(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    trend = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    event = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN)
    assert trend.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    assert event.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    # per_trade_budget=5000 each; total_requested=10000; cap=6000 -> scale=0.6, both scaled identically.
    assert trend.portfolio_allocated_risk == event.portfolio_allocated_risk == Decimal("3000.0")


def test_same_symbol_opposite_direction_both_count_fully_no_netting() -> None:
    """TREND_FOLLOWING LONG_CANDIDATE, EVENT_DRIVEN SHORT_CANDIDATE, same
    symbol - both count fully toward total_requested (no cancellation),
    producing the identical scaling outcome as the same-direction case."""
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
    )
    directions = {r.family: r.direction for r in judge_result.family_results}
    assert directions[StrategyFamily.TREND_FOLLOWING] != directions[StrategyFamily.EVENT_DRIVEN]

    snapshot = default_account_snapshot(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    trend = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    event = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN)
    assert trend.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    assert event.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    # Identical to the same-direction case - no netting applied whatsoever.
    assert trend.portfolio_allocated_risk == event.portfolio_allocated_risk == Decimal("3000.0")
