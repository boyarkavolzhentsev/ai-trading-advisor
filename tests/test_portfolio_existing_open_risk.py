"""Stage 8: existing open portfolio risk (``current_open_risk_to_stop``)
partially consumes, exactly consumes, and exceeds the portfolio capacity."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily

from tests.market_evaluation_support import full_technical_result
from tests.portfolio_support import route_judge_gate_risk_and_portfolio
from tests.risk_gate_support import default_account_snapshot

_ROLLOVER_EQUITY = Decimal("1000000")  # ample Stage 7 daily/per-trade headroom
_CURRENT_EQUITY = Decimal("100000")  # portfolio cap = 100,000 * 6% = 6000


def _trend_result(current_open_risk_to_stop: Decimal):
    snapshot = default_account_snapshot(
        rollover_equity=_ROLLOVER_EQUITY, current_equity=_CURRENT_EQUITY, current_open_risk_to_stop=current_open_risk_to_stop
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=full_technical_result(), account_snapshot=snapshot, risk_per_unit=Decimal("10")
    )
    return next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def test_existing_open_risk_partially_consumes_capacity() -> None:
    # cap=6000, open_risk=3000 -> remaining=3000 < per-trade ceiling (5000) -> scaled to 3000.
    trend = _trend_result(Decimal("3000"))
    assert trend.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    assert trend.portfolio_allocated_risk == Decimal("3000.000")


def test_existing_open_risk_exactly_consumes_capacity() -> None:
    # cap=6000, open_risk=6000 -> remaining=0 exactly -> blocked.
    trend = _trend_result(Decimal("6000"))
    assert trend.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert trend.reasons == (PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,)
    assert trend.portfolio_allocated_risk is None


def test_existing_open_risk_exceeds_capacity() -> None:
    # cap=6000, open_risk=9000 -> remaining floored at 0 (never negative) -> blocked.
    trend = _trend_result(Decimal("9000"))
    assert trend.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert trend.reasons == (PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,)
    assert trend.portfolio_allocated_risk is None
