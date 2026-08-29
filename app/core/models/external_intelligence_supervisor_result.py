"""Stage 4G deterministic external-intelligence-supervisor output contract.

Aggregates already-produced Stage 4F ``ExternalIntelligenceAnalysisResult``
objects for one analysis pass. Deliberately narrower than
``FlowSupervisorResult``/``TechnicalSupervisorResult``: Stage 4F results
share no single identity anchor (Macro/Rates are scoped by ``currency``,
News by ``symbol``, On-Chain by ``asset``+``network``), so this model
preserves each result's own native scope rather than fabricating one shared
anchor. It reports analyst-*type* participation, per-scope quality, and a
plain index back into the embedded results - it never reads, interprets, or
promotes any individual ``ExternalIntelligenceDimension`` value.

Every embedded ``ExternalIntelligenceAnalysisResult`` is carried unchanged:
the Supervisor never re-grades, re-derives, launders, or selectively
surfaces Stage 4F evidence/quality/observations - it only counts and
cross-references what Stage 4F already produced. No new evidence is minted
here, and no supervisor-level observation reference exists: the only pointer
this model contributes is ``ExternalIntelligenceScopeSummary.result_index``,
which resolves into the embedded ``analysis_results`` tuple; the rest of the
evidence chain (observations -> evidence_refs -> ``ExternalIntelligenceEvidence``)
is Stage 4F's own, untouched.

This model can structurally never carry a ``TradeDirection``, a score, a
weight, a confidence, an agreement/contradiction verdict, or a free-text
market verdict.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceOutcome
from app.core.enums.external_intelligence_supervisor import ExternalIntelligenceSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.economic_event import CurrencyCode
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.instrument import Asset

_CURRENCY_SCOPED = (ExternalIntelligenceAnalystType.MACRO_EVENT, ExternalIntelligenceAnalystType.RATES_YIELD)


class ExternalIntelligenceScopeSummary(DomainModel):
    """One canonical ``(analyst_type, native_scope)`` participation/quality entry.

    Carries no observation content, interpretation, agreement/contradiction
    verdict, direction, confidence, strength, score, weight, recommendation,
    copied evidence, or copied abstention reasons - only the bookkeeping
    needed to locate and trust exactly one embedded Stage 4F result.
    """

    analyst_type: ExternalIntelligenceAnalystType
    currency: CurrencyCode | None = None
    symbol: Symbol | None = None
    asset: Asset | None = None
    network: str | None = None
    result_outcome: ExternalIntelligenceOutcome
    quality: FeatureQuality
    result_index: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_scope_shape(self) -> Self:
        if self.analyst_type in _CURRENCY_SCOPED:
            if self.currency is None:
                raise ValueError(f"{self.analyst_type.value} scope summary requires currency")
            if self.symbol is not None or self.asset is not None or self.network is not None:
                raise ValueError(f"{self.analyst_type.value} scope summary must not carry symbol/asset/network")
        elif self.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
            if self.symbol is None:
                raise ValueError("NEWS_SENTIMENT scope summary requires symbol")
            if self.currency is not None or self.asset is not None or self.network is not None:
                raise ValueError("NEWS_SENTIMENT scope summary must not carry currency/asset/network")
        elif self.analyst_type is ExternalIntelligenceAnalystType.ON_CHAIN:
            if self.asset is None or self.network is None:
                raise ValueError("ON_CHAIN scope summary requires both asset and network")
            if self.currency is not None or self.symbol is not None:
                raise ValueError("ON_CHAIN scope summary must not carry currency/symbol")
        return self


class ExternalIntelligenceSupervisorResult(DomainModel):
    """Deterministic aggregation of one analysis pass's Stage 4F results
    across the expected analyst-type set. Participation + scope + quality +
    traceability only - no semantic reconciliation of any kind."""

    analysis_time: Timestamp

    outcome: ExternalIntelligenceSupervisorOutcome

    expected_analyst_types: tuple[ExternalIntelligenceAnalystType, ...] = Field(min_length=1)
    analyzed_analyst_types: tuple[ExternalIntelligenceAnalystType, ...] = Field(default_factory=tuple)
    abstained_analyst_types: tuple[ExternalIntelligenceAnalystType, ...] = Field(default_factory=tuple)
    missing_analyst_types: tuple[ExternalIntelligenceAnalystType, ...] = Field(default_factory=tuple)

    total_input_results: int = Field(ge=0)
    total_analyzed_results: int = Field(ge=0)
    total_abstained_results: int = Field(ge=0)

    overall_quality: FeatureQuality

    scope_summaries: tuple[ExternalIntelligenceScopeSummary, ...] = Field(default_factory=tuple)
    analysis_results: tuple[ExternalIntelligenceAnalysisResult, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_expected_analyst_types_unique(self) -> Self:
        if len(set(self.expected_analyst_types)) != len(self.expected_analyst_types):
            raise ValueError("expected_analyst_types must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_participation_partitions_expected(self) -> Self:
        expected = set(self.expected_analyst_types)
        analyzed = set(self.analyzed_analyst_types)
        abstained = set(self.abstained_analyst_types)
        missing = set(self.missing_analyst_types)

        for name, bucket, bucket_set in (
            ("analyzed_analyst_types", self.analyzed_analyst_types, analyzed),
            ("abstained_analyst_types", self.abstained_analyst_types, abstained),
            ("missing_analyst_types", self.missing_analyst_types, missing),
        ):
            if len(bucket_set) != len(bucket):
                raise ValueError(f"{name} must not contain duplicates")

        if not analyzed.isdisjoint(abstained) or not analyzed.isdisjoint(missing) or not abstained.isdisjoint(missing):
            raise ValueError("an analyst type must belong to exactly one participation bucket")

        if (analyzed | abstained | missing) != expected:
            raise ValueError("analyzed/abstained/missing must exactly partition expected_analyst_types")

        return self

    @model_validator(mode="after")
    def _validate_result_counts(self) -> Self:
        if self.total_input_results != len(self.analysis_results):
            raise ValueError("total_input_results must equal len(analysis_results)")
        if self.total_input_results != len(self.scope_summaries):
            raise ValueError("total_input_results must equal len(scope_summaries)")

        analyzed_summaries = sum(1 for s in self.scope_summaries if s.result_outcome is ExternalIntelligenceOutcome.ANALYZED)
        abstained_summaries = sum(1 for s in self.scope_summaries if s.result_outcome is ExternalIntelligenceOutcome.ABSTAINED)

        if self.total_analyzed_results != analyzed_summaries:
            raise ValueError("total_analyzed_results must equal the number of ANALYZED scope_summaries")
        if self.total_abstained_results != abstained_summaries:
            raise ValueError("total_abstained_results must equal the number of ABSTAINED scope_summaries")
        if self.total_analyzed_results + self.total_abstained_results != self.total_input_results:
            raise ValueError("total_analyzed_results + total_abstained_results must equal total_input_results")

        return self

    @model_validator(mode="after")
    def _validate_scope_summaries_reference_results(self) -> Self:
        for summary in self.scope_summaries:
            if summary.result_index < 0 or summary.result_index >= len(self.analysis_results):
                raise ValueError(f"scope_summary references invalid result index {summary.result_index}")

            result = self.analysis_results[summary.result_index]

            if summary.analyst_type is not result.analyst_type:
                raise ValueError(
                    f"scope_summary analyst_type {summary.analyst_type} does not match "
                    f"referenced result analyst_type {result.analyst_type}"
                )
            if (
                summary.currency != result.currency
                or summary.symbol != result.symbol
                or summary.asset != result.asset
                or summary.network != result.network
            ):
                raise ValueError(f"scope_summary native scope does not match referenced result at index {summary.result_index}")
            if summary.result_outcome is not result.status:
                raise ValueError(
                    f"scope_summary result_outcome does not match referenced result status at index {summary.result_index}"
                )
            if summary.quality is not result.quality:
                raise ValueError(f"scope_summary quality does not match referenced result quality at index {summary.result_index}")

        return self

    @model_validator(mode="after")
    def _validate_participation_matches_scope_summaries(self) -> Self:
        analyzed_types = {s.analyst_type for s in self.scope_summaries if s.result_outcome is ExternalIntelligenceOutcome.ANALYZED}
        types_with_any_result = {s.analyst_type for s in self.scope_summaries}
        abstained_types = types_with_any_result - analyzed_types
        missing_types = set(self.expected_analyst_types) - types_with_any_result

        if set(self.analyzed_analyst_types) != analyzed_types & set(self.expected_analyst_types):
            raise ValueError("analyzed_analyst_types does not match analyst types with at least one ANALYZED result")
        if set(self.abstained_analyst_types) != abstained_types & set(self.expected_analyst_types):
            raise ValueError(
                "abstained_analyst_types does not match analyst types with at least one result but none ANALYZED"
            )
        if set(self.missing_analyst_types) != missing_types:
            raise ValueError("missing_analyst_types does not match analyst types with no supplied result")

        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        expected_count = len(self.expected_analyst_types)
        analyzed_count = len(self.analyzed_analyst_types)

        if analyzed_count == 0:
            expected_outcome = ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE
        elif analyzed_count == expected_count:
            expected_outcome = ExternalIntelligenceSupervisorOutcome.ANALYZED
        else:
            expected_outcome = ExternalIntelligenceSupervisorOutcome.PARTIAL

        if self.outcome is not expected_outcome:
            raise ValueError(f"outcome {self.outcome} does not match participation-derived outcome {expected_outcome}")

        return self

    @model_validator(mode="after")
    def _validate_overall_quality(self) -> Self:
        analyzed_qualities = [
            result.quality for result in self.analysis_results if result.status is ExternalIntelligenceOutcome.ANALYZED
        ]
        if not analyzed_qualities:
            expected_quality = FeatureQuality.UNAVAILABLE
        else:
            severity = {
                FeatureQuality.VALID: 0,
                FeatureQuality.PARTIAL: 1,
                FeatureQuality.STALE: 2,
                FeatureQuality.UNAVAILABLE: 3,
            }
            expected_quality = max(analyzed_qualities, key=lambda q: severity[q])

        if self.overall_quality is not expected_quality:
            raise ValueError(f"overall_quality {self.overall_quality} does not match expected fold {expected_quality}")

        return self


__all__ = ["ExternalIntelligenceScopeSummary", "ExternalIntelligenceSupervisorResult"]
