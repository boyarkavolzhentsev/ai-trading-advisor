"""Stage 6C traceability: quality is resolved from exactly the Judge
evidence refs a family carries, through both Technical and External
contours, role-agnostically."""

from __future__ import annotations

from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import JudgeContour
from app.core.enums.strategy_router import StrategyFamily
from tests.market_evaluation_support import make_context
from tests.policy_gate_support import route_judge_and_gate, technical_trend_with_quality
from tests.strategy_judge_support import external_with_news_sentiment


def test_quality_resolved_from_exact_judge_refs_technical() -> None:
    """Every judge_evidence_ref_index on a blocked TREND_FOLLOWING result
    corresponds exactly to the (contour, analyst_result_index,
    observation_index) of the matching JudgeEvidenceRef, resolved through
    the embedded market evaluation - never a coarser contour-level quality."""
    _, judge_result, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.STALE))
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    trend_policy = next(r for r in policy_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)

    market_evaluation = judge_result.strategy_router_result.market_evaluation
    for violation in trend_policy.quality_violations:
        ref = trend_judge.evidence_refs[violation.judge_evidence_ref_index]
        assert ref.contour is JudgeContour.TECHNICAL
        observation = market_evaluation.technical.analyst_results[ref.analyst_result_index].observations[ref.observation_index]
        assert observation.quality is violation.resolved_quality
        assert violation.resolved_quality is FeatureQuality.STALE


def test_technical_ref_resolution_path() -> None:
    _, judge_result, policy_result = route_judge_and_gate(technical=technical_trend_with_quality(quality=FeatureQuality.VALID))
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert all(ref.contour is JudgeContour.TECHNICAL for ref in trend_judge.evidence_refs)
    trend_policy = next(r for r in policy_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_policy.quality_violations == ()


def test_external_ref_resolution_path() -> None:
    _, judge_result, policy_result = route_judge_and_gate(
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}), context=make_context()
    )
    event_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN)
    event_policy = next(r for r in policy_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN)
    assert all(ref.contour is JudgeContour.EXTERNAL for ref in event_judge.evidence_refs)

    market_evaluation = judge_result.strategy_router_result.market_evaluation
    for index, ref in enumerate(event_judge.evidence_refs):
        observation = market_evaluation.external.analysis_results[ref.analyst_result_index].observations[ref.observation_index]
        # This fixture is built entirely with VALID evidence - no violations expected.
        assert observation.quality is FeatureQuality.VALID
    assert event_policy.quality_violations == ()


def test_role_agnostic_evidence_quality_handling() -> None:
    """Every evidence_ref a DIRECTIONAL family carries - regardless of
    EvidenceRole - is subject to the identical quality rule: this is proven
    by resolving quality generically over the whole evidence_refs tuple with
    no role-based branch anywhere in the implementation."""
    import ast
    import inspect
    from pathlib import Path

    from app.decision.gate import PolicyGate

    path = Path(inspect.getfile(PolicyGate))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "role":
            raise AssertionError("gate.py inspects EvidenceRole - quality resolution must be role-agnostic")
