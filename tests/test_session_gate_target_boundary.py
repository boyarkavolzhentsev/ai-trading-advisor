"""Stage 9: rollover-based session TARGET_REACHED boundary.

target_profit_amount = rollover_equity * target_profit_percent / 100
current_session_pnl = current_equity - rollover_equity
TARGET_REACHED iff current_session_pnl >= target_profit_amount (exact
equality counts). current_equity is mark-to-market inclusive, so this is
deliberately floating-PnL-inclusive.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.session import TradingSessionStatus
from tests.session_support import route_to_portfolio_and_session

_ROLLOVER_EQUITY = Decimal("100000")
_TARGET_PROFIT_PERCENT = Decimal("6.0")  # TradingCycleConfig default
_TARGET_AMOUNT = _ROLLOVER_EQUITY * _TARGET_PROFIT_PERCENT / Decimal("100")  # 6000


def _status_for_current_equity(current_equity: Decimal) -> TradingSessionStatus:
    from tests.risk_gate_support import default_account_snapshot

    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, current_equity=current_equity)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    return session_result.session_status


def test_below_target_is_active() -> None:
    status = _status_for_current_equity(_ROLLOVER_EQUITY + _TARGET_AMOUNT - Decimal("0.01"))
    assert status is TradingSessionStatus.ACTIVE


def test_exactly_at_target_is_reached() -> None:
    status = _status_for_current_equity(_ROLLOVER_EQUITY + _TARGET_AMOUNT)
    assert status is TradingSessionStatus.TARGET_REACHED


def test_above_target_is_reached() -> None:
    status = _status_for_current_equity(_ROLLOVER_EQUITY + _TARGET_AMOUNT + Decimal("0.01"))
    assert status is TradingSessionStatus.TARGET_REACHED


def test_floating_pnl_inclusive_via_current_equity() -> None:
    """current_equity alone (not realized_daily_pnl/floating_pnl) drives the
    target check - a purely floating (unrealized) gain that pushes
    current_equity past the target still triggers TARGET_REACHED."""
    from tests.risk_gate_support import default_account_snapshot

    snapshot = default_account_snapshot(
        rollover_equity=_ROLLOVER_EQUITY,
        current_equity=_ROLLOVER_EQUITY + _TARGET_AMOUNT,
        realized_daily_pnl=Decimal("0"),
        floating_pnl=Decimal("0"),
    )
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert session_result.session_status is TradingSessionStatus.TARGET_REACHED
