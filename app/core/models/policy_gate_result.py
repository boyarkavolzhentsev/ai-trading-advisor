"""Stage 6C deterministic Policy/Safety Gate output contract.

Aggregates one already-produced ``StrategyJudgeResult`` into a per-eligible-
``StrategyFamily`` system-policy verdict: whether that family's Judge thesis
is structurally and policy-wise allowed to proceed to downstream Risk/Money-
Management review. This model validates structural consistency only (Judge-
outcome/block-reason coupling, evidence-quality-violation shape/bounds/
exactness, family coverage, top-level-outcome derivation) - it never
reinterprets what any cited observation's raw value means, since that would
duplicate Judge's own semantic mapping logic one stage back; only the
already-graded ``FeatureQuality`` of each observation Judge actually cited is
ever inspected here.

The embedded ``StrategyJudgeResult`` (and, through it,
``StrategyRouterResult``/``MarketEvaluationResult``) is carried unchanged: no
evidence, observation, direction, or provenance is ever copied out of it -
every ``PolicyFamilyResult`` back-references its family only, and every
``PolicyEvidenceQualityViolation`` is a typed index into the matching
``JudgeFamilyResult.evidence_refs``, never a copy of the referenced
``JudgeEvidenceRef`` itself.

Passing Stage 6C (``PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW``) means only
that one family's Judge thesis may proceed to Risk/Money-Management review -
never that a trade, position, or execution of any kind has been approved.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.policy_gate import PolicyBlockReason, PolicyFamilyVerdict, PolicyGateOutcome
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import JudgeContour, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel
from app.core.models.strategy_judge_result import JudgeEvidenceRef, JudgeFamilyResult, StrategyJudgeResult

_REASON_ORDER: tuple[PolicyBlockReason, ...] = tuple(PolicyBlockReason)

_ALLOWED_EVIDENCE_QUALITIES: frozenset[FeatureQuality] = frozenset({FeatureQuality.VALID, FeatureQuality.PARTIAL})
"""Stage 6C V1 fixed policy: VALID/PARTIAL evidence may proceed, STALE/
UNAVAILABLE evidence may not. A tiny, locally-owned constant - not caller
configuration, mirroring the repository's precedent of each stage
reimplementing its own narrow policy primitive rather than sharing one
cross-stage (see ``app.strategies.router._USABLE_QUALITIES``). Deliberately
not imported from ``app.decision.gate`` (whose own ``PolicyGate.apply``
independently re-derives the identical allowlist to produce its output) -
mirrors the Stage 5A/6A precedent of the operational component and the
result model's self-validation maintaining independent copies of the same
tiny primitive rather than cross-importing one from the other."""


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


class PolicyEvidenceQualityViolation(DomainModel):
    """One pointer from a blocked ``DIRECTIONAL`` family verdict to the exact
    Judge evidence reference whose resolved observation quality fell outside
    the Stage 6C allowlist.

    ``judge_evidence_ref_index`` indexes into the matching
    ``JudgeFamilyResult.evidence_refs`` - no evidence is ever copied, only
    indexed, mirroring ``JudgeEvidenceRef`` itself one stage back. No family
    index is carried: family/index correspondence is already enforced by
    ``StrategyPolicyResult.family_results``.
    """

    judge_evidence_ref_index: int = Field(ge=0)
    resolved_quality: FeatureQuality


class PolicyFamilyResult(DomainModel):
    """One Router-eligible strategy family's Stage 6C policy verdict.

    ``reasons`` is empty if and only if ``verdict`` is
    ``ELIGIBLE_FOR_RISK_REVIEW``; when non-empty it is canonically ordered
    (``PolicyBlockReason`` declaration order) and duplicate-free.
    ``quality_violations`` is non-empty if and only if
    ``PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY`` is present in
    ``reasons``. Carries no direction, evidence, score, confidence, or
    free-text explanation - direction remains accessible only through the
    embedded ``StrategyJudgeResult`` on ``StrategyPolicyResult``.
    """

    family: StrategyFamily
    verdict: PolicyFamilyVerdict
    reasons: tuple[PolicyBlockReason, ...] = ()
    quality_violations: tuple[PolicyEvidenceQualityViolation, ...] = ()

    @model_validator(mode="after")
    def _validate_verdict_matches_reasons(self) -> Self:
        expected = PolicyFamilyVerdict.BLOCKED if self.reasons else PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
        if self.verdict is not expected:
            raise ValueError("verdict must be BLOCKED iff reasons is non-empty")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.reasons]
        if indexes != sorted(indexes):
            raise ValueError("reasons must be in canonical PolicyBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("reasons must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_quality_violations_require_reason(self) -> Self:
        has_reason = PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY in self.reasons
        if bool(self.quality_violations) != has_reason:
            raise ValueError("quality_violations must be non-empty iff DISALLOWED_EVIDENCE_QUALITY is present in reasons")
        return self

    @model_validator(mode="after")
    def _validate_quality_violations_canonical_and_unique(self) -> Self:
        indexes = [violation.judge_evidence_ref_index for violation in self.quality_violations]
        if indexes != sorted(indexes):
            raise ValueError("quality_violations must be ordered by ascending judge_evidence_ref_index")
        if len(set(indexes)) != len(indexes):
            raise ValueError("quality_violations must not contain duplicate judge_evidence_ref_index values")
        return self


class StrategyPolicyResult(DomainModel):
    """Deterministic Stage 6C aggregation: one policy verdict per
    ``StrategyJudgeResult.family_results`` entry, plus the
    participation-derived top-level outcome."""

    strategy_judge_result: StrategyJudgeResult
    outcome: PolicyGateOutcome
    family_results: tuple[PolicyFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_judge_family_results(self) -> Self:
        expected = tuple(result.family for result in self.strategy_judge_result.family_results)
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly strategy_judge_result.family_results, in the same order")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        any_eligible = any(result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW for result in self.family_results)
        expected = PolicyGateOutcome.SOME_ELIGIBLE_FOR_RISK_REVIEW if any_eligible else PolicyGateOutcome.NO_ELIGIBLE_FAMILY
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match per-family-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_family_verdicts_match_judge_outcome(self) -> Self:
        for judge_result, policy_result in zip(self.strategy_judge_result.family_results, self.family_results, strict=True):
            if judge_result.outcome is JudgeOutcome.MIXED:
                self._validate_structural_block(judge_result, policy_result, PolicyBlockReason.JUDGE_OUTCOME_MIXED)
            elif judge_result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE:
                self._validate_structural_block(
                    judge_result, policy_result, PolicyBlockReason.JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE
                )
            else:
                self._validate_directional_family(judge_result, policy_result)
        return self

    @staticmethod
    def _validate_structural_block(
        judge_result: JudgeFamilyResult, policy_result: PolicyFamilyResult, reason: PolicyBlockReason
    ) -> None:
        if policy_result.verdict is not PolicyFamilyVerdict.BLOCKED:
            raise ValueError(f"family {policy_result.family}: {judge_result.outcome} Judge outcome must be BLOCKED")
        if policy_result.reasons != (reason,):
            raise ValueError(f"family {policy_result.family}: {judge_result.outcome} Judge outcome must carry exactly ({reason},)")

    def _validate_directional_family(self, judge_result: JudgeFamilyResult, policy_result: PolicyFamilyResult) -> None:
        resolved_by_index = {
            index: _resolve_observation_quality(self.strategy_judge_result, ref)
            for index, ref in enumerate(judge_result.evidence_refs)
        }
        expected_violations = {
            index: quality for index, quality in resolved_by_index.items() if quality not in _ALLOWED_EVIDENCE_QUALITIES
        }

        if not expected_violations:
            if policy_result.verdict is not PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW:
                raise ValueError(
                    f"family {policy_result.family}: DIRECTIONAL Judge outcome with allowed evidence quality "
                    "must be ELIGIBLE_FOR_RISK_REVIEW"
                )
            return

        if policy_result.verdict is not PolicyFamilyVerdict.BLOCKED:
            raise ValueError(
                f"family {policy_result.family}: DIRECTIONAL Judge outcome with disallowed evidence quality must be BLOCKED"
            )
        if policy_result.reasons != (PolicyBlockReason.DISALLOWED_EVIDENCE_QUALITY,):
            raise ValueError(f"family {policy_result.family}: disallowed-quality block must carry exactly (DISALLOWED_EVIDENCE_QUALITY,)")

        actual_violations = {v.judge_evidence_ref_index: v.resolved_quality for v in policy_result.quality_violations}
        if actual_violations != expected_violations:
            raise ValueError(
                f"family {policy_result.family}: quality_violations do not exactly match the disallowed-quality evidence_refs"
            )


__all__ = ["PolicyEvidenceQualityViolation", "PolicyFamilyResult", "StrategyPolicyResult"]
