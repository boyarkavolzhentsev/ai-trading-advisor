"""Stage 5A deterministic market-evaluation output contract.

Aggregates already-produced Flow/Technical/External-Intelligence supervisor
results for one explicit ``MarketEvaluationContext`` and ``evaluation_time``.
Deliberately narrower than any of the three upstream supervisor contracts:
this model reports contour participation, per-contour quality, and which
External Intelligence scopes are structurally relevant to this context - it
never compares what any contour's evidence *says*, and it can structurally
never carry a direction, score, weight, confidence, or trading
recommendation of any kind.

Every embedded supervisor result is carried unchanged: this model never
re-grades, re-derives, or launders Flow/Technical/External evidence or
quality - it only counts, normalizes participation, and structurally aligns
External Intelligence's heterogeneous native scopes against the caller's
explicit context. No new evidence is ever minted here, and no
``MarketEvaluationEvidence`` model exists: the only pointer this model
contributes is ``ExternalScopeAlignmentRef.scope_summary_index``, which
resolves into the embedded ``external.scope_summaries`` tuple; the rest of
the evidence chain (Stage 4G's own ``result_index`` through Stage 4A-4E
provenance) is untouched.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.market_evaluation import (
    ExternalAlignmentStatus,
    ExternalScopeMatchKind,
    MarketEvaluationContourStatus,
    MarketEvaluationOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Timestamp
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult

_CURRENCY_SCOPED_ANALYST_TYPES = (
    ExternalIntelligenceAnalystType.MACRO_EVENT,
    ExternalIntelligenceAnalystType.RATES_YIELD,
)

_QUALIFYING_STATUSES = (MarketEvaluationContourStatus.ANALYZED, MarketEvaluationContourStatus.PARTIAL)

_QUALITY_SEVERITY: dict[FeatureQuality, int] = {
    FeatureQuality.VALID: 0,
    FeatureQuality.PARTIAL: 1,
    FeatureQuality.STALE: 2,
    FeatureQuality.UNAVAILABLE: 3,
}
"""A tiny, locally-owned severity fold - not imported from any Flow/
Technical/External contour package, matching this repository's own
precedent of each contour reimplementing this primitive rather than
sharing it cross-contour."""


def _worse_of_many(qualities: list[FeatureQuality]) -> FeatureQuality:
    result = FeatureQuality.VALID
    for quality in qualities:
        if _QUALITY_SEVERITY[quality] > _QUALITY_SEVERITY[result]:
            result = quality
    return result


class ExternalScopeAlignmentRef(DomainModel):
    """One pointer from a matched Stage 4G scope to the explicit
    ``MarketEvaluationContext`` field it was matched on. Bookkeeping only -
    no evidence, no semantic content, no score, no confidence, no
    direction."""

    scope_summary_index: int = Field(ge=0)
    matched_by: ExternalScopeMatchKind


class MarketEvaluationResult(DomainModel):
    """Deterministic aggregation of one evaluation's Flow/Technical/External
    Intelligence supervisor results. Participation + quality + structural
    scope alignment + traceability only - no semantic reconciliation of any
    kind."""

    evaluation_time: Timestamp
    context: MarketEvaluationContext

    outcome: MarketEvaluationOutcome

    flow_status: MarketEvaluationContourStatus
    technical_status: MarketEvaluationContourStatus
    external_status: MarketEvaluationContourStatus

    flow_quality: FeatureQuality | None
    technical_quality: FeatureQuality | None
    external_quality: FeatureQuality | None

    overall_quality: FeatureQuality

    flow: FlowSupervisorResult | None
    technical: TechnicalSupervisorResult | None
    external: ExternalIntelligenceSupervisorResult | None

    external_alignment_status: ExternalAlignmentStatus
    external_scope_alignment: tuple[ExternalScopeAlignmentRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_flow_contour(self) -> Self:
        if self.flow is None:
            if self.flow_status is not MarketEvaluationContourStatus.MISSING:
                raise ValueError("flow_status must be MISSING when flow is None")
            if self.flow_quality is not None:
                raise ValueError("flow_quality must be None when flow is None")
        else:
            expected_status = MarketEvaluationContourStatus(self.flow.outcome.value)
            if self.flow_status is not expected_status:
                raise ValueError(f"flow_status {self.flow_status} does not match flow.outcome {self.flow.outcome}")
            if self.flow_quality is not self.flow.overall_quality:
                raise ValueError("flow_quality must equal flow.overall_quality")
        return self

    @model_validator(mode="after")
    def _validate_technical_contour(self) -> Self:
        if self.technical is None:
            if self.technical_status is not MarketEvaluationContourStatus.MISSING:
                raise ValueError("technical_status must be MISSING when technical is None")
            if self.technical_quality is not None:
                raise ValueError("technical_quality must be None when technical is None")
        else:
            expected_status = MarketEvaluationContourStatus(self.technical.outcome.value)
            if self.technical_status is not expected_status:
                raise ValueError(
                    f"technical_status {self.technical_status} does not match technical.outcome {self.technical.outcome}"
                )
            if self.technical_quality is not self.technical.overall_quality:
                raise ValueError("technical_quality must equal technical.overall_quality")
        return self

    @model_validator(mode="after")
    def _validate_external_contour(self) -> Self:
        if self.external is None:
            if self.external_status is not MarketEvaluationContourStatus.MISSING:
                raise ValueError("external_status must be MISSING when external is None")
            if self.external_quality is not None:
                raise ValueError("external_quality must be None when external is None")
        else:
            expected_status = MarketEvaluationContourStatus(self.external.outcome.value)
            if self.external_status is not expected_status:
                raise ValueError(
                    f"external_status {self.external_status} does not match external.outcome {self.external.outcome}"
                )
            if self.external_quality is not self.external.overall_quality:
                raise ValueError("external_quality must equal external.overall_quality")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        statuses = (self.flow_status, self.technical_status, self.external_status)
        if all(status is MarketEvaluationContourStatus.ANALYZED for status in statuses):
            expected = MarketEvaluationOutcome.EVALUATED
        elif any(status in _QUALIFYING_STATUSES for status in statuses):
            expected = MarketEvaluationOutcome.PARTIAL
        else:
            expected = MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE

        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match participation-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_overall_quality(self) -> Self:
        qualifying_qualities = [
            quality
            for status, quality in (
                (self.flow_status, self.flow_quality),
                (self.technical_status, self.technical_quality),
                (self.external_status, self.external_quality),
            )
            if status in _QUALIFYING_STATUSES and quality is not None
        ]
        expected = _worse_of_many(qualifying_qualities) if qualifying_qualities else FeatureQuality.UNAVAILABLE
        if self.overall_quality is not expected:
            raise ValueError(f"overall_quality {self.overall_quality} does not match expected fold {expected}")
        return self

    @model_validator(mode="after")
    def _validate_external_alignment_status(self) -> Self:
        if self.external is None:
            if self.external_alignment_status is not ExternalAlignmentStatus.MISSING:
                raise ValueError("external_alignment_status must be MISSING when external is None")
            if self.external_scope_alignment:
                raise ValueError("external_scope_alignment must be empty when external is None")
        elif not self.external_scope_alignment:
            if self.external_alignment_status is not ExternalAlignmentStatus.NO_MATCHING_SCOPE:
                raise ValueError("external_alignment_status must be NO_MATCHING_SCOPE when no scopes matched")
        else:
            if self.external_alignment_status is not ExternalAlignmentStatus.MATCHED:
                raise ValueError("external_alignment_status must be MATCHED when at least one scope matched")
        return self

    @model_validator(mode="after")
    def _validate_alignment_indexes(self) -> Self:
        if self.external is None:
            return self
        scope_count = len(self.external.scope_summaries)
        for ref in self.external_scope_alignment:
            if ref.scope_summary_index >= scope_count:
                raise ValueError(f"external_scope_alignment references invalid scope index {ref.scope_summary_index}")
        return self

    @model_validator(mode="after")
    def _validate_matched_by_consistency(self) -> Self:
        if self.external is None:
            return self
        for ref in self.external_scope_alignment:
            scope = self.external.scope_summaries[ref.scope_summary_index]
            if ref.matched_by is ExternalScopeMatchKind.SYMBOL:
                if scope.analyst_type is not ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
                    raise ValueError("SYMBOL matched_by requires a NEWS_SENTIMENT scope")
                if scope.symbol != self.context.symbol:
                    raise ValueError("SYMBOL matched_by scope.symbol does not equal context.symbol")
            elif ref.matched_by is ExternalScopeMatchKind.ASSET_NETWORK:
                if scope.analyst_type is not ExternalIntelligenceAnalystType.ON_CHAIN:
                    raise ValueError("ASSET_NETWORK matched_by requires an ON_CHAIN scope")
                if self.context.base_asset is None or self.context.network is None:
                    raise ValueError("ASSET_NETWORK matched_by requires context.base_asset and context.network")
                if scope.asset != self.context.base_asset or scope.network != self.context.network:
                    raise ValueError("ASSET_NETWORK matched_by scope does not equal context.base_asset/network")
            elif ref.matched_by is ExternalScopeMatchKind.CURRENCY:
                if scope.analyst_type not in _CURRENCY_SCOPED_ANALYST_TYPES:
                    raise ValueError("CURRENCY matched_by requires a MACRO_EVENT or RATES_YIELD scope")
                if scope.currency not in self.context.currency_exposures:
                    raise ValueError("CURRENCY matched_by scope.currency not in context.currency_exposures")
        return self


__all__ = ["ExternalScopeAlignmentRef", "MarketEvaluationResult"]
