"""Stage 9 family gating matrix: Stage-8-blocked families stay blocked
regardless of session status; ACTIVE passes through unscaled; every other
status blocks every otherwise-eligible family identically (global, no
divergence, no priority)."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict
from app.statistics.session import SessionGate
from tests.session_support import route_to_portfolio_and_session, three_family_portfolio_result


def test_portfolio_blocked_family_can_never_become_session_eligible() -> None:
    portfolio_result, session_result = route_to_portfolio_and_session()
    blocked_portfolio_families = {
        r.family for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    }
    assert blocked_portfolio_families, "fixture must include at least one Portfolio-blocked family"
    for result in session_result.family_results:
        if result.family in blocked_portfolio_families:
            assert result.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
            assert result.reasons == (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)
            assert result.session_allocated_risk is None


def test_portfolio_blocked_family_stays_blocked_even_when_session_locked() -> None:
    _, session_result = route_to_portfolio_and_session(locked_override=True)
    for result in session_result.family_results:
        if result.reasons == (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,):
            assert result.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION


def test_active_session_passes_through_allocation_unscaled() -> None:
    portfolio_result, session_result = route_to_portfolio_and_session()
    assert session_result.session_status is TradingSessionStatus.ACTIVE
    portfolio_eligible = {
        r.family: r.portfolio_allocated_risk
        for r in portfolio_result.family_results
        if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    }
    for result in session_result.family_results:
        if result.family in portfolio_eligible:
            assert result.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW
            assert result.reasons == ()
            assert result.session_allocated_risk == portfolio_eligible[result.family]


def test_blocked_session_status_sets_allocation_to_none() -> None:
    _, session_result = route_to_portfolio_and_session(locked_override=True)
    for result in session_result.family_results:
        if result.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION:
            assert result.session_allocated_risk is None


def test_multiple_families_share_identical_global_status_no_divergence() -> None:
    # three_family_portfolio_result's own rollover_equity default is 1,000,000
    # (ample Stage 7/8 headroom); target = 1,000,000 * 6% = 60,000.
    portfolio_result = three_family_portfolio_result(current_equity=Decimal("1060000"))
    session_result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=False)
    assert session_result.session_status is TradingSessionStatus.TARGET_REACHED

    eligible_upstream = [
        r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    ]
    assert len(eligible_upstream) >= 2, "fixture must exercise at least two simultaneously Portfolio-eligible families"
    downstream_by_family = {r.family: r for r in session_result.family_results}
    for upstream in eligible_upstream:
        downstream = downstream_by_family[upstream.family]
        assert downstream.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
        assert downstream.reasons == (SessionBlockReason.TARGET_REACHED,)


def test_multiple_families_no_first_come_priority() -> None:
    """No family is favored by position/order: every eligible family gets
    the identical verdict/reason for a given global session status."""
    portfolio_result = three_family_portfolio_result()
    session_result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=False)
    assert session_result.session_status is TradingSessionStatus.ACTIVE

    eligible = [r for r in session_result.family_results if r.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW]
    assert len(eligible) >= 2
    for result in eligible:
        assert result.reasons == ()
