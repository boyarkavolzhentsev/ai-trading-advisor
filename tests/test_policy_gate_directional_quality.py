"""Stage 6C quality policy over DIRECTIONAL family verdicts: VALID/PARTIAL
allowed, STALE/UNAVAILABLE blocked, exhaustive per-ref violations."""

from __future__ import annotations

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily
from tests.policy_gate_support import route_judge_and_gate, technical_trend_with_quality


def _trend_result(policy_result):
    return next(result for result in policy_result.family_results if result.family is StrategyFamily.TREND_FOLLOWING)


def test_directional_valid_evidence_eligible() -> None:
    _, _, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.VALID))
    trend = _trend_result(policy_result)
    assert trend.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert trend.reasons == ()
    assert trend.quality_violations == ()


def test_directional_partial_evidence_eligible() -> None:
    _, _, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.PARTIAL))
    trend = _trend_result(policy_result)
    assert trend.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert trend.reasons == ()


def test_directional_valid_partial_mixture_eligible() -> None:
    """RETURN_DIRECTION VALID on both timeframes, SLOPE_DIRECTION PARTIAL on
    both - a genuine per-observation quality mixture, still all allowed."""
    from app.core.enums.market import Timeframe
    from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
    from app.technical_supervisor.supervisor import TechnicalSupervisor
    from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

    results = []
    for timeframe in DEFAULT_TIMEFRAMES[:2]:
        observations = (
            make_observation(
                dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD", quality=FeatureQuality.VALID
            ),
            make_observation(
                dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION, value="UPWARD", quality=FeatureQuality.PARTIAL
            ),
        )
        results.append(
            analyzed_result(TechnicalAnalystType.TREND, timeframe, observations=observations, quality=FeatureQuality.PARTIAL)
        )
    technical = TechnicalSupervisor().aggregate(tuple(results))

    _, _, policy_result = route_judge_and_gate(technical=technical)
    trend = _trend_result(policy_result)
    assert trend.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert trend.reasons == ()


def test_directional_stale_evidence_blocked() -> None:
    _, judge_result, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.STALE))
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    trend = _trend_result(policy_result)
    assert trend.verdict is PolicyFamilyVerdict.BLOCKED
    assert trend.reasons == (PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,)
    assert len(trend.quality_violations) == len(trend_judge.evidence_refs)
    assert all(v.resolved_quality is FeatureQuality.STALE for v in trend.quality_violations)


def test_directional_unavailable_evidence_blocked_defensively() -> None:
    """Observation-level UNAVAILABLE on an otherwise ANALYZED result - a
    structurally reachable state (per-observation quality is independent of
    the enclosing result's own quality field) that must never silently pass."""
    _, judge_result, policy_result = route_judge_and_gate(
        technical=technical_trend_with_quality(quality=FeatureQuality.UNAVAILABLE, result_quality=FeatureQuality.VALID)
    )
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    trend = _trend_result(policy_result)
    assert trend.verdict is PolicyFamilyVerdict.BLOCKED
    assert trend.reasons == (PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,)
    assert len(trend.quality_violations) == len(trend_judge.evidence_refs)
    assert all(v.resolved_quality is FeatureQuality.UNAVAILABLE for v in trend.quality_violations)


def test_multiple_disallowed_refs_produce_exhaustive_violations() -> None:
    """Four cited refs (RETURN_DIRECTION + SLOPE_DIRECTION x 2 timeframes),
    all STALE - every one must appear exactly once."""
    _, judge_result, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.STALE))
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    trend = _trend_result(policy_result)
    assert len(trend_judge.evidence_refs) == 4
    violation_indexes = [v.judge_evidence_ref_index for v in trend.quality_violations]
    assert violation_indexes == list(range(4))
