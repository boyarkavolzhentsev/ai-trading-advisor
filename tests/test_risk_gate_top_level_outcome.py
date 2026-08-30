"""Stage 7 top-level outcome: fully derived from per-family verdicts, no
third state, no selected/preferred family."""

from __future__ import annotations

from app.core.enums.risk_gate import RiskFamilyVerdict, RiskGateOutcome
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, route_judge_gate_and_risk
from decimal import Decimal


def test_no_eligible_family_yields_no_risk_eligible_family_outcome() -> None:
    _, risk_result = route_judge_gate_and_risk()
    assert risk_result.family_results == ()
    assert risk_result.outcome is RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY


def test_all_blocked_by_daily_limit_yields_no_risk_eligible_family() -> None:
    snapshot = default_account_snapshot(realized_daily_pnl=Decimal("-1500"))
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result(), account_snapshot=snapshot)
    assert all(r.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK for r in risk_result.family_results)
    assert risk_result.outcome is RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY


def test_at_least_one_eligible_yields_some_eligible_outcome() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    assert any(r.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW for r in risk_result.family_results)
    assert risk_result.outcome is RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW


def test_outcome_has_no_third_state() -> None:
    assert set(RiskGateOutcome) == {
        RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW,
        RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY,
    }
