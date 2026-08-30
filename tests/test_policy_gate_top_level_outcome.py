"""Stage 6C top-level outcome: fully derived from per-family verdicts, no
third state, no ranking/winner."""

from __future__ import annotations

from app.core.enums.policy_gate import PolicyFamilyVerdict, PolicyGateOutcome
from tests.market_evaluation_support import full_technical_result
from tests.policy_gate_support import route_judge_and_gate


def test_no_eligible_family_yields_no_eligible_family_outcome() -> None:
    """Empty evaluation - zero eligible families at all, so zero eligible
    PolicyFamilyResult entries."""
    _, _, policy_result = route_judge_and_gate()
    assert policy_result.family_results == ()
    assert policy_result.outcome is PolicyGateOutcome.NO_ELIGIBLE_FAMILY


def test_all_blocked_families_yield_no_eligible_family_outcome() -> None:
    """Technical-only: TREND_FOLLOWING directional+clean is normally
    eligible, but MEAN_REVERSION always blocks - force TREND_FOLLOWING to
    MIXED too so every family is blocked."""
    from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
    from app.technical_supervisor.supervisor import TechnicalSupervisor
    from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

    results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            DEFAULT_TIMEFRAMES[0],
            observations=(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),),
        ),
        analyzed_result(
            TechnicalAnalystType.TREND,
            DEFAULT_TIMEFRAMES[1],
            observations=(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="DOWNWARD"),),
        ),
    ]
    technical = TechnicalSupervisor().aggregate(tuple(results))
    _, _, policy_result = route_judge_and_gate(technical=technical)
    assert all(result.verdict is PolicyFamilyVerdict.BLOCKED for result in policy_result.family_results)
    assert policy_result.outcome is PolicyGateOutcome.NO_ELIGIBLE_FAMILY


def test_at_least_one_eligible_yields_some_eligible_outcome() -> None:
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    assert any(result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW for result in policy_result.family_results)
    assert policy_result.outcome is PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW


def test_outcome_has_no_third_state() -> None:
    assert set(PolicyGateOutcome) == {PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW, PolicyGateOutcome.NO_ELIGIBLE_FAMILY}
