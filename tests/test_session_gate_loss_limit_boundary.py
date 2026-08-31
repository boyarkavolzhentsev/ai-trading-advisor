"""Stage 9: LOSS_LIMIT_REACHED reporting boundary.

Stage 9 re-derives Stage 7's own daily-loss-capacity formula exactly (never
a second threshold) purely to expose the correct ``TradingSessionStatus``:

daily_loss_limit = rollover_equity * daily_risk_limit_percent / 100
current_daily_pnl = realized_daily_pnl + floating_pnl
loss_consumed = max(0, -current_daily_pnl)
remaining_daily_loss_capacity = max(0, daily_loss_limit - loss_consumed)
LOSS_LIMIT_REACHED iff remaining_daily_loss_capacity <= 0
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.session import TradingSessionStatus
from tests.risk_gate_support import default_account_snapshot
from tests.session_support import route_to_portfolio_and_session

_ROLLOVER_EQUITY = Decimal("100000")
_DAILY_RISK_LIMIT_PERCENT = Decimal("1.5")  # TradingCycleConfig default
_DAILY_LOSS_LIMIT = _ROLLOVER_EQUITY * _DAILY_RISK_LIMIT_PERCENT / Decimal("100")  # 1500


def _status_for_realized_pnl(realized_daily_pnl: Decimal) -> TradingSessionStatus:
    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, realized_daily_pnl=realized_daily_pnl)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    return session_result.session_status


def test_below_loss_boundary_is_active() -> None:
    status = _status_for_realized_pnl(-(_DAILY_LOSS_LIMIT - Decimal("0.01")))
    assert status is TradingSessionStatus.ACTIVE


def test_exactly_at_loss_boundary_is_reached() -> None:
    status = _status_for_realized_pnl(-_DAILY_LOSS_LIMIT)
    assert status is TradingSessionStatus.LOSS_LIMIT_REACHED


def test_beyond_loss_boundary_is_reached() -> None:
    status = _status_for_realized_pnl(-(_DAILY_LOSS_LIMIT + Decimal("100")))
    assert status is TradingSessionStatus.LOSS_LIMIT_REACHED


def test_floating_loss_counts_toward_boundary() -> None:
    snapshot = default_account_snapshot(
        rollover_equity=_ROLLOVER_EQUITY, realized_daily_pnl=Decimal("0"), floating_pnl=-_DAILY_LOSS_LIMIT
    )
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert session_result.session_status is TradingSessionStatus.LOSS_LIMIT_REACHED


def test_no_family_eligible_for_session_review_still_reports_loss_limit_reached() -> None:
    """Stage 7 already blocks every family globally when the daily-loss
    capacity is exhausted, so no family reaching Stage 9 can itself carry
    that reason - but the top-level session_status must still correctly
    report LOSS_LIMIT_REACHED even when StrategyPortfolioResult carries zero
    eligible families."""
    from app.core.enums.portfolio import PortfolioFamilyVerdict

    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, realized_daily_pnl=-_DAILY_LOSS_LIMIT)
    portfolio_result, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert all(r.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO for r in portfolio_result.family_results)
    assert session_result.session_status is TradingSessionStatus.LOSS_LIMIT_REACHED
