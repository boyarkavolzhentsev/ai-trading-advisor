"""Stage 9: exact status precedence - LOCKED > LOSS_LIMIT_REACHED >
TARGET_REACHED > ACTIVE.

``AccountRiskSnapshot`` places no cross-field consistency requirement
between ``current_equity`` and ``realized_daily_pnl``/``floating_pnl``, so
loss-limit and target conditions can be crafted independently to exercise
every precedence combination.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.session import TradingSessionStatus
from tests.risk_gate_support import default_account_snapshot
from tests.session_support import route_to_portfolio_and_session

_ROLLOVER_EQUITY = Decimal("100000")
_LOSS_REACHED_PNL = Decimal("-1500")  # exactly at the 1.5% default daily-loss boundary
_TARGET_REACHED_EQUITY = Decimal("106000")  # exactly at the 6% default target boundary


def test_locked_and_target_reached_together_yields_locked() -> None:
    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, current_equity=_TARGET_REACHED_EQUITY)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot, locked_override=True)
    assert session_result.session_status is TradingSessionStatus.LOCKED


def test_locked_and_loss_reached_together_yields_locked() -> None:
    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, realized_daily_pnl=_LOSS_REACHED_PNL)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot, locked_override=True)
    assert session_result.session_status is TradingSessionStatus.LOCKED


def test_loss_reached_and_target_reached_together_yields_loss_limit_reached() -> None:
    snapshot = default_account_snapshot(
        rollover_equity=_ROLLOVER_EQUITY, current_equity=_TARGET_REACHED_EQUITY, realized_daily_pnl=_LOSS_REACHED_PNL
    )
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert session_result.session_status is TradingSessionStatus.LOSS_LIMIT_REACHED


def test_target_reached_only_yields_target_reached() -> None:
    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY, current_equity=_TARGET_REACHED_EQUITY)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert session_result.session_status is TradingSessionStatus.TARGET_REACHED


def test_neither_condition_yields_active() -> None:
    snapshot = default_account_snapshot(rollover_equity=_ROLLOVER_EQUITY)
    _, session_result = route_to_portfolio_and_session(account_snapshot=snapshot)
    assert session_result.session_status is TradingSessionStatus.ACTIVE
