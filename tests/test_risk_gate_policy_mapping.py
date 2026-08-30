"""Stage 7 Policy-verdict mapping: a Policy-BLOCKED family maps exactly to
``POLICY_NOT_ELIGIBLE`` and never receives/accepts a candidate."""

from __future__ import annotations

from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import route_judge_gate_and_risk


def test_policy_blocked_family_maps_to_policy_not_eligible() -> None:
    policy_result, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    mean_reversion_policy = next(
        r for r in policy_result.family_results if r.family is StrategyFamily.MEAN_REVERSION
    )
    assert mean_reversion_policy.verdict is PolicyFamilyVerdict.BLOCKED

    mean_reversion_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.MEAN_REVERSION)
    assert mean_reversion_risk.verdict.value == "BLOCKED_BY_RISK"
    assert mean_reversion_risk.reasons[0].value == "POLICY_NOT_ELIGIBLE"
    assert len(mean_reversion_risk.reasons) == 1
    assert mean_reversion_risk.max_individual_risk is None
    assert mean_reversion_risk.recommended_units is None


def test_no_candidate_supplied_for_policy_blocked_family() -> None:
    """default_candidates_for only builds candidates for eligible families -
    confirms none was built/needed for the blocked MEAN_REVERSION family."""
    policy_result, _ = route_judge_gate_and_risk(technical=full_technical_result())
    eligible_families = {
        r.family for r in policy_result.family_results if r.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    }
    assert StrategyFamily.MEAN_REVERSION not in eligible_families
