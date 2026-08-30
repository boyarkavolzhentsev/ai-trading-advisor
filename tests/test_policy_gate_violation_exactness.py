"""Stage 6C ``StrategyPolicyResult`` must reject any hand-constructed
``quality_violations`` set that is not exactly the disallowed-quality Judge
evidence refs: out-of-bounds indexes, mismatched ``resolved_quality``,
allowed-quality entries, missing entries, and extra entries must all be
rejected. Hand construction is appropriate here: these are deliberately
malformed/unreachable states that ``PolicyGate`` itself would never build."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict, PolicyGateOutcome
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.policy_gate_result import PolicyEvidenceQualityViolation, PolicyFamilyResult, StrategyPolicyResult
from app.decision.gate import PolicyGate
from app.judge.judge import Judge
from app.strategies.router import StrategyRouter
from tests.policy_gate_support import technical_trend_with_quality
from tests.strategy_router_support import evaluation


def _stale_trend_judge_result():
    """A real DIRECTIONAL TREND_FOLLOWING JudgeFamilyResult built entirely
    from STALE evidence - exactly 4 evidence_refs, all disallowed."""
    router_result = StrategyRouter().route(
        market_evaluation=evaluation(technical=technical_trend_with_quality(quality=FeatureQuality.STALE))
    )
    judge_result = Judge().judge(strategy_router_result=router_result)
    trend = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert len(trend.evidence_refs) == 4
    return judge_result


def _other_family_results(judge_result):
    """The correctly-gated result for every family besides TREND_FOLLOWING,
    reused unmodified so only the TREND_FOLLOWING entry under test varies."""
    reference = PolicyGate().apply(strategy_judge_result=judge_result)
    return tuple(r for r in reference.family_results if r.family is not StrategyFamily.TREND_FOLLOWING)


def _assemble(judge_result, trend_family_result) -> StrategyPolicyResult:
    others = _other_family_results(judge_result)
    family_results = (trend_family_result, *others)
    # Restore canonical order (TREND_FOLLOWING is always first among eligible families here).
    outcome = (
        PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW
        if any(r.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW for r in family_results)
        else PolicyGateOutcome.NO_ELIGIBLE_FAMILY
    )
    return StrategyPolicyResult(strategy_judge_result=judge_result, outcome=outcome, family_results=family_results)


def test_correct_exhaustive_violations_accepted() -> None:
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=tuple(
            PolicyEvidenceQualityViolation(judge_evidence_ref_index=i, resolved_quality=FeatureQuality.STALE)
            for i in range(4)
        ),
    )
    result = _assemble(judge_result, trend)
    assert result.family_results[0] is trend


def test_out_of_bounds_violation_index_rejected() -> None:
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=(PolicyEvidenceQualityViolation(judge_evidence_ref_index=99, resolved_quality=FeatureQuality.STALE),),
    )
    with pytest.raises(ValidationError):
        _assemble(judge_result, trend)


def test_mismatched_resolved_quality_rejected() -> None:
    """Index 0 genuinely resolves to STALE - claiming UNAVAILABLE must fail."""
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=tuple(
            PolicyEvidenceQualityViolation(
                judge_evidence_ref_index=i, resolved_quality=FeatureQuality.UNAVAILABLE if i == 0 else FeatureQuality.STALE
            )
            for i in range(4)
        ),
    )
    with pytest.raises(ValidationError):
        _assemble(judge_result, trend)


def test_allowed_quality_cannot_appear_as_violation() -> None:
    """Index 0 genuinely resolves to STALE - falsely claiming it resolved to
    the allowed VALID must fail (VALID is not a legitimate violation entry
    for any index, and cannot substitute for the real STALE entry)."""
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=tuple(
            PolicyEvidenceQualityViolation(
                judge_evidence_ref_index=i, resolved_quality=FeatureQuality.VALID if i == 0 else FeatureQuality.STALE
            )
            for i in range(4)
        ),
    )
    with pytest.raises(ValidationError):
        _assemble(judge_result, trend)


def test_missing_violation_for_disallowed_ref_rejected() -> None:
    """Only 3 of the 4 disallowed refs are reported - not exhaustive."""
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=tuple(
            PolicyEvidenceQualityViolation(judge_evidence_ref_index=i, resolved_quality=FeatureQuality.STALE)
            for i in range(3)
        ),
    )
    with pytest.raises(ValidationError):
        _assemble(judge_result, trend)


def test_extra_violation_rejected() -> None:
    """A fifth violation entry with an out-of-bounds index padded on top of
    an otherwise-correct exhaustive set must still fail (also covered by the
    out-of-bounds case, but this asserts the "exactness", not just bounds,
    check catches a superfluous-but-in-range-shaped addition too)."""
    judge_result = _stale_trend_judge_result()
    trend = PolicyFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=tuple(
            PolicyEvidenceQualityViolation(judge_evidence_ref_index=i, resolved_quality=FeatureQuality.STALE)
            for i in range(5)
        ),
    )
    with pytest.raises(ValidationError):
        _assemble(judge_result, trend)
