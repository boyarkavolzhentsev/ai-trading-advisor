"""Stage 6B deterministic Judge output contract.

Aggregates one already-produced ``StrategyRouterResult`` into a per-eligible-
``StrategyFamily`` semantic verdict: what the allowed evidence actually means
for that family, expressed only as ``JudgeOutcome`` + an optional
``DirectionalCandidate`` + typed evidence references. This model validates
structural consistency only (outcome/direction coupling, evidence-ref
shape/bounds, family coverage) - it does not and cannot re-derive whether a
cited observation's raw value truly supports the claimed direction, since
that would duplicate ``Judge``'s own dimension-specific mapping logic;
semantic correctness is exercised by ``Judge``'s own test suite instead,
exactly as no upstream stage's result model re-verifies its producer's
arithmetic.

The embedded ``StrategyRouterResult`` (and, through it, ``MarketEvaluationResult``)
is carried unchanged: no evidence, observation, or provenance is ever copied
out of it - every reference is a typed index, mirroring
``TechnicalCoherenceResult.evidence_refs``'s own ``(result_index,
observation_index)`` shape one layer up.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.strategy_judge import DirectionalCandidate, EvidenceRole, JudgeContour, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel
from app.core.models.strategy_router_result import StrategyRouterResult

_CONTOUR_ORDER: tuple[JudgeContour, ...] = tuple(JudgeContour)
_ROLE_ORDER: tuple[EvidenceRole, ...] = tuple(EvidenceRole)


class JudgeEvidenceRef(DomainModel):
    """One typed pointer from a Judge conclusion to an upstream observation.

    Resolves into ``market_evaluation.{technical.analyst_results,
    flow.analyst_results, external.analysis_results}[analyst_result_index]
    .observations[observation_index]`` depending on ``contour`` - no
    evidence is ever copied, only indexed.
    """

    contour: JudgeContour
    role: EvidenceRole
    analyst_result_index: int = Field(ge=0)
    observation_index: int = Field(ge=0)


class JudgeFamilyResult(DomainModel):
    """One eligible strategy family's semantic verdict.

    ``direction`` exists if and only if ``outcome`` is ``DIRECTIONAL``.
    Carries no confidence, score, weight, rank, probability, free-text
    reasoning, explanation, metadata dict, or timestamp.
    """

    family: StrategyFamily
    outcome: JudgeOutcome
    direction: DirectionalCandidate | None = None
    evidence_refs: tuple[JudgeEvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _validate_direction_matches_outcome(self) -> Self:
        if self.outcome is JudgeOutcome.DIRECTIONAL:
            if self.direction is None:
                raise ValueError("DIRECTIONAL outcome requires a non-None direction")
        elif self.direction is not None:
            raise ValueError(f"{self.outcome} outcome must not carry a direction")
        return self

    @model_validator(mode="after")
    def _validate_insufficient_evidence_has_no_refs(self) -> Self:
        if self.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE and self.evidence_refs:
            raise ValueError("INSUFFICIENT_EVIDENCE must not carry evidence_refs")
        return self

    @model_validator(mode="after")
    def _validate_directional_has_primary_ref(self) -> Self:
        if self.outcome is JudgeOutcome.DIRECTIONAL:
            if not any(ref.role is EvidenceRole.PRIMARY for ref in self.evidence_refs):
                raise ValueError("DIRECTIONAL outcome requires at least one PRIMARY evidence_ref")
        return self

    @model_validator(mode="after")
    def _validate_mixed_has_demonstrated_conflict(self) -> Self:
        if self.outcome is JudgeOutcome.MIXED and len(self.evidence_refs) < 2:
            raise ValueError("MIXED outcome requires at least two evidence_refs demonstrating a conflict")
        return self

    @model_validator(mode="after")
    def _validate_evidence_refs_canonical_and_unique(self) -> Self:
        keys = [
            (_CONTOUR_ORDER.index(ref.contour), _ROLE_ORDER.index(ref.role), ref.analyst_result_index, ref.observation_index)
            for ref in self.evidence_refs
        ]
        if keys != sorted(keys):
            raise ValueError("evidence_refs must be in canonical (contour, role, analyst_result_index, observation_index) order")
        if len(set(keys)) != len(keys):
            raise ValueError("evidence_refs must not contain duplicates")
        return self


class StrategyJudgeResult(DomainModel):
    """Deterministic Stage 6B aggregation: one semantic verdict per
    Router-eligible ``StrategyFamily``. No family outside
    ``strategy_router_result.eligible_families`` may ever appear."""

    strategy_router_result: StrategyRouterResult
    family_results: tuple[JudgeFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_eligible_families(self) -> Self:
        expected = self.strategy_router_result.eligible_families
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly eligible_families, in canonical order")
        return self

    @model_validator(mode="after")
    def _validate_evidence_refs_in_bounds(self) -> Self:
        market_evaluation = self.strategy_router_result.market_evaluation
        contour_lengths = {
            JudgeContour.TECHNICAL: len(market_evaluation.technical.analyst_results) if market_evaluation.technical else None,
            JudgeContour.FLOW: len(market_evaluation.flow.analyst_results) if market_evaluation.flow else None,
            JudgeContour.EXTERNAL: len(market_evaluation.external.analysis_results) if market_evaluation.external else None,
        }

        def _observation_count(contour: JudgeContour, analyst_result_index: int) -> int:
            if contour is JudgeContour.TECHNICAL:
                return len(market_evaluation.technical.analyst_results[analyst_result_index].observations)
            if contour is JudgeContour.FLOW:
                return len(market_evaluation.flow.analyst_results[analyst_result_index].observations)
            return len(market_evaluation.external.analysis_results[analyst_result_index].observations)

        for result in self.family_results:
            for ref in result.evidence_refs:
                total = contour_lengths[ref.contour]
                if total is None:
                    raise ValueError(f"evidence_ref references unavailable contour {ref.contour} for family {result.family}")
                if ref.analyst_result_index >= total:
                    raise ValueError(
                        f"evidence_ref references invalid analyst_result_index {ref.analyst_result_index} for contour {ref.contour}"
                    )
                observation_count = _observation_count(ref.contour, ref.analyst_result_index)
                if ref.observation_index >= observation_count:
                    raise ValueError(
                        f"evidence_ref references invalid observation_index {ref.observation_index} "
                        f"for contour {ref.contour} analyst_result_index {ref.analyst_result_index}"
                    )
        return self


__all__ = ["JudgeEvidenceRef", "JudgeFamilyResult", "StrategyJudgeResult"]
