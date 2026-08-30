"""Stage 6C result-model self-validation: ``PolicyEvidenceQualityViolation``,
``PolicyFamilyResult`` and ``StrategyPolicyResult`` invariants, frozen/
extra-forbid behavior. Malformed externally-constructed objects must be
rejected - not only objects ``PolicyGate`` itself would build."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict, PolicyGateOutcome
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.policy_gate_result import PolicyEvidenceQualityViolation, PolicyFamilyResult, StrategyPolicyResult
from tests.market_evaluation_support import full_technical_result
from tests.policy_gate_support import route_judge_and_gate

# --- PolicyFamilyResult: verdict/reasons coupling ---


def test_eligible_forbids_reasons() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW,
            reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED,),
        )


def test_blocked_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PolicyFamilyVerdict.BLOCKED, reasons=())


def test_eligible_with_no_reasons_accepted() -> None:
    result = PolicyFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW)
    assert result.reasons == ()


def test_blocked_with_one_reason_accepted() -> None:
    result = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED,),
    )
    assert result.reasons == (PolicyBlockReason.JUDGE_OUTCOME_MIXED,)


# --- reasons: canonical order / duplicate-free ---


def test_duplicate_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED, PolicyBlockReason.JUDGE_OUTCOME_MIXED),
        )


def test_non_canonical_reason_order_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY, PolicyBlockReason.JUDGE_OUTCOME_MIXED),
        )


# --- quality_violations: require DISALLOWED_EVIDENCE_QUALITY reason ---

_VIOLATION_A = PolicyEvidenceQualityViolation(judge_evidence_ref_index=0, resolved_quality=FeatureQuality.STALE)
_VIOLATION_B = PolicyEvidenceQualityViolation(judge_evidence_ref_index=1, resolved_quality=FeatureQuality.UNAVAILABLE)


def test_quality_violations_without_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED,),
            quality_violations=(_VIOLATION_A,),
        )


def test_disallowed_quality_reason_without_violations_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
            quality_violations=(),
        )


def test_disallowed_quality_reason_with_violations_accepted() -> None:
    result = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=(_VIOLATION_A,),
    )
    assert result.quality_violations == (_VIOLATION_A,)


# --- quality_violations: ordering / duplicate-free ---


def test_violation_ordering_enforced() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
            quality_violations=(_VIOLATION_B, _VIOLATION_A),
        )


def test_duplicate_violation_index_rejected() -> None:
    duplicate = PolicyEvidenceQualityViolation(judge_evidence_ref_index=0, resolved_quality=FeatureQuality.UNAVAILABLE)
    with pytest.raises(ValidationError):
        PolicyFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
            quality_violations=(_VIOLATION_A, duplicate),
        )


def test_violation_negative_index_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicyEvidenceQualityViolation(judge_evidence_ref_index=-1, resolved_quality=FeatureQuality.STALE)


def test_violation_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        PolicyEvidenceQualityViolation(judge_evidence_ref_index=0, resolved_quality=FeatureQuality.STALE, confidence=0.9)


# --- frozen / extra-forbid ---


def test_family_result_frozen() -> None:
    result = PolicyFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW)
    with pytest.raises(ValidationError):
        result.verdict = PolicyFamilyVerdict.BLOCKED


def test_family_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        PolicyFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW, confidence=0.9)


def test_violation_frozen() -> None:
    with pytest.raises(ValidationError):
        _VIOLATION_A.resolved_quality = FeatureQuality.VALID


# --- StrategyPolicyResult: family coverage / outcome derivation ---


def _base_judge_result(**kwargs):
    from app.judge.judge import Judge
    from app.strategies.router import StrategyRouter
    from tests.strategy_router_support import evaluation

    router_result = StrategyRouter().route(market_evaluation=evaluation(**kwargs))
    return Judge().judge(strategy_router_result=router_result)


def test_family_results_must_match_judge_family_results() -> None:
    judge_result = _base_judge_result(technical=full_technical_result())
    with pytest.raises(ValidationError):
        StrategyPolicyResult(
            strategy_judge_result=judge_result, outcome=PolicyGateOutcome.NO_ELIGIBLE_FAMILY, family_results=()
        )


def test_family_results_wrong_order_rejected() -> None:
    judge_result = _base_judge_result(technical=full_technical_result())
    trend = PolicyFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW)
    reversion = PolicyFamilyResult(
        family=StrategyFamily.MEAN_REVERSION,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE,),
    )
    with pytest.raises(ValidationError):
        StrategyPolicyResult(
            strategy_judge_result=judge_result,
            outcome=PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW,
            family_results=(reversion, trend),
        )


def test_inconsistent_top_level_outcome_rejected() -> None:
    """A judge result with one DIRECTIONAL/clean family: claiming
    NO_ELIGIBLE_FAMILY while a family is ELIGIBLE_FOR_RISK_REVIEW must fail."""
    _, judge_result, policy_result = route_judge_and_gate(technical=full_technical_result())
    wrong_outcome = PolicyGateOutcome.NO_ELIGIBLE_FAMILY if policy_result.outcome is PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW else PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW
    with pytest.raises(ValidationError):
        StrategyPolicyResult(
            strategy_judge_result=judge_result, outcome=wrong_outcome, family_results=policy_result.family_results
        )


def test_correct_top_level_outcome_accepted() -> None:
    _, judge_result, policy_result = route_judge_and_gate(technical=full_technical_result())
    rebuilt = StrategyPolicyResult(
        strategy_judge_result=judge_result, outcome=policy_result.outcome, family_results=policy_result.family_results
    )
    assert rebuilt == policy_result


def test_frozen() -> None:
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    with pytest.raises(ValidationError):
        policy_result.outcome = PolicyGateOutcome.NO_ELIGIBLE_FAMILY


def test_extra_fields_forbidden() -> None:
    judge_result = _base_judge_result(technical=full_technical_result())
    with pytest.raises(ValidationError):
        StrategyPolicyResult(
            strategy_judge_result=judge_result,
            outcome=PolicyGateOutcome.NO_ELIGIBLE_FAMILY,
            family_results=(),
            confidence=0.9,
        )
