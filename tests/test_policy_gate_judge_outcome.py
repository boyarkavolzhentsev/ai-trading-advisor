"""Stage 6C Judge-outcome policy: MIXED and INSUFFICIENT_EVIDENCE are always
blocked, with their own exact reason, and never perform quality gating."""

from __future__ import annotations

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict
from app.core.enums.strategy_judge import JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from tests.policy_gate_support import route_judge_and_gate


def test_mean_reversion_always_insufficient_evidence_and_blocked() -> None:
    """MEAN_REVERSION always abstains in Judge V1 - the canonical
    INSUFFICIENT_EVIDENCE case with zero evidence_refs to gate."""
    from tests.market_evaluation_support import full_technical_result

    _, judge_result, policy_result = route_judge_and_gate(technical=full_technical_result())
    judge_mr = next(r for r in judge_result.family_results if r.family is StrategyFamily.MEAN_REVERSION)
    policy_mr = next(r for r in policy_result.family_results if r.family is StrategyFamily.MEAN_REVERSION)
    assert judge_mr.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert policy_mr.verdict is PolicyFamilyVerdict.BLOCKED
    assert policy_mr.reasons == (PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE,)
    assert policy_mr.quality_violations == ()


def test_mixed_judge_outcome_blocked_with_exact_reason() -> None:
    """Conflicting RETURN_DIRECTION across two timeframes forces MIXED."""
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

    _, judge_result, policy_result = route_judge_and_gate(technical=technical)
    judge_trend = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    policy_trend = next(r for r in policy_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert judge_trend.outcome is JudgeOutcome.MIXED
    assert policy_trend.verdict is PolicyFamilyVerdict.BLOCKED
    assert policy_trend.reasons == (PolicyBlockReason.JUDGE_OUTCOME_MIXED,)
    assert policy_trend.quality_violations == ()


def test_mixed_outcome_ignores_evidence_quality() -> None:
    """Even if the conflicting evidence is STALE, the block reason is
    JUDGE_OUTCOME_MIXED, never DISALLOWED_EVIDENCE_QUALITY - quality gating
    only applies within the DIRECTIONAL branch."""
    from app.core.enums.quality import FeatureQuality
    from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
    from app.technical_supervisor.supervisor import TechnicalSupervisor
    from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

    results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            DEFAULT_TIMEFRAMES[0],
            observations=(
                make_observation(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD", quality=FeatureQuality.STALE
                ),
            ),
            quality=FeatureQuality.STALE,
        ),
        analyzed_result(
            TechnicalAnalystType.TREND,
            DEFAULT_TIMEFRAMES[1],
            observations=(
                make_observation(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="DOWNWARD", quality=FeatureQuality.STALE
                ),
            ),
            quality=FeatureQuality.STALE,
        ),
    ]
    technical = TechnicalSupervisor().aggregate(tuple(results))

    _, judge_result, policy_result = route_judge_and_gate(technical=technical)
    judge_trend = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    policy_trend = next(r for r in policy_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert judge_trend.outcome is JudgeOutcome.MIXED
    assert policy_trend.reasons == (PolicyBlockReason.JUDGE_OUTCOME_MIXED,)
    assert policy_trend.quality_violations == ()
