"""Deterministic Policy/Safety Gate (Stage 6C).

Applies deterministic system policy over one already-produced
``StrategyJudgeResult``: whether each family Judge produced a result for is
structurally and policy-wise allowed to proceed to downstream Risk/Money-
Management review. Never invokes Router or Judge, never touches a Flow/
Technical/External Intelligence analyst or supervisor package, never
performs I/O - a pure, synchronous, stateless function of its input (see
``app.decision.protocols.PolicyGateProtocol``).

Reads only ``JudgeOutcome`` and the already-graded ``FeatureQuality`` of the
exact observations Judge cited via ``JudgeFamilyResult.evidence_refs`` -
never a Flow/Technical/External Intelligence observation's own ``.value``,
never contour-level quality. Whether a family's evidence quality is VALID,
PARTIAL, STALE, or UNAVAILABLE is exactly the information this gate is
allowed to act on; what any observation's value actually says is Judge's
question, answered one stage back, never re-asked here.

Quality resolution is role-agnostic: every ``JudgeEvidenceRef`` a
``JudgeFamilyResult`` carries is subject to the identical Stage 6C quality
rule, regardless of ``EvidenceRole``.

Each eligible family is evaluated entirely independently: no family's Judge
outcome, direction, or evidence quality ever influences another's Stage 6C
verdict, mirroring Judge's own no-cross-family-voting discipline one stage
over. No ranking, no winner, no vote, no confidence, no capital sizing, no
portfolio exposure math, no broker/execution dependency of any kind.
"""

from __future__ import annotations

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict, PolicyGateOutcome
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import JudgeContour, JudgeOutcome
from app.core.models.policy_gate_result import PolicyEvidenceQualityViolation, PolicyFamilyResult, StrategyPolicyResult
from app.core.models.strategy_judge_result import JudgeEvidenceRef, JudgeFamilyResult, StrategyJudgeResult

_ALLOWED_EVIDENCE_QUALITIES: frozenset[FeatureQuality] = frozenset({FeatureQuality.VALID, FeatureQuality.PARTIAL})
"""Stage 6C V1 fixed policy - a locally-owned copy, not imported from
``app.core.models.policy_gate_result`` (whose own model validator
independently re-derives the identical allowlist to self-validate its own
fields), mirroring the Stage 5A/6A precedent of the operational component and
the result model's self-validation maintaining independent copies of the
same tiny primitive rather than cross-importing one from the other."""


def _resolve_observation_quality(strategy_judge_result: StrategyJudgeResult, ref: JudgeEvidenceRef) -> FeatureQuality:
    """Resolve one ``JudgeEvidenceRef`` to the ``FeatureQuality`` of the exact
    observation it points at - never the coarser contour-level quality, and
    never the observation's ``.value``."""
    market_evaluation = strategy_judge_result.strategy_router_result.market_evaluation
    if ref.contour is JudgeContour.TECHNICAL:
        analyst_result = market_evaluation.technical.analyst_results[ref.analyst_result_index]
    elif ref.contour is JudgeContour.FLOW:
        analyst_result = market_evaluation.flow.analyst_results[ref.analyst_result_index]
    else:
        analyst_result = market_evaluation.external.analysis_results[ref.analyst_result_index]
    return analyst_result.observations[ref.observation_index].quality


def _evaluate_family(strategy_judge_result: StrategyJudgeResult, judge_result: JudgeFamilyResult) -> PolicyFamilyResult:
    if judge_result.outcome is JudgeOutcome.MIXED:
        return PolicyFamilyResult(
            family=judge_result.family,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.JUDGE_OUTCOME_MIXED,),
        )

    if judge_result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE:
        return PolicyFamilyResult(
            family=judge_result.family,
            verdict=PolicyFamilyVerdict.BLOCKED,
            reasons=(PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE,),
        )

    violations = tuple(
        PolicyEvidenceQualityViolation(judge_evidence_ref_index=index, resolved_quality=quality)
        for index, ref in enumerate(judge_result.evidence_refs)
        if (quality := _resolve_observation_quality(strategy_judge_result, ref)) not in _ALLOWED_EVIDENCE_QUALITIES
    )

    if not violations:
        return PolicyFamilyResult(family=judge_result.family, verdict=PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW)

    return PolicyFamilyResult(
        family=judge_result.family,
        verdict=PolicyFamilyVerdict.BLOCKED,
        reasons=(PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,),
        quality_violations=violations,
    )


class PolicyGate:
    """Deterministic Stage 6C aggregator over one ``StrategyJudgeResult``."""

    def apply(self, *, strategy_judge_result: StrategyJudgeResult) -> StrategyPolicyResult:
        family_results = tuple(
            _evaluate_family(strategy_judge_result, judge_result) for judge_result in strategy_judge_result.family_results
        )
        any_eligible = any(result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW for result in family_results)
        outcome = PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW if any_eligible else PolicyGateOutcome.NO_ELIGIBLE_FAMILY

        return StrategyPolicyResult(
            strategy_judge_result=strategy_judge_result,
            outcome=outcome,
            family_results=family_results,
        )


__all__ = ["PolicyGate"]
