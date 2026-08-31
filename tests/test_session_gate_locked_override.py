"""Stage 9: locked_override explicit operator/runtime kill-switch."""

from __future__ import annotations

from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionFamilyVerdict, SessionGateOutcome
from tests.session_support import route_to_portfolio_and_session


def test_locked_override_false_does_not_lock() -> None:
    _, session_result = route_to_portfolio_and_session(locked_override=False)
    assert session_result.session_status is not TradingSessionStatus.LOCKED
    assert session_result.locked_override is False


def test_locked_override_true_locks_regardless_of_account_state() -> None:
    _, session_result = route_to_portfolio_and_session(locked_override=True)
    assert session_result.session_status is TradingSessionStatus.LOCKED
    assert session_result.locked_override is True


def test_locked_override_true_blocks_every_family() -> None:
    _, session_result = route_to_portfolio_and_session(locked_override=True)
    assert session_result.outcome is SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY
    for result in session_result.family_results:
        assert result.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
        assert result.session_allocated_risk is None
