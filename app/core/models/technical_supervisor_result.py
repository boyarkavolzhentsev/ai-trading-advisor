"""Stage 3C deterministic technical-supervisor output contract.

Aggregates already-produced Stage 3B ``TechnicalAnalysisResult`` objects
spanning multiple ``(analyst_type, timeframe)`` cells for one common
``(symbol, contract_type, observation_time)`` evaluation. Deliberately a
parallel model family to the Stage 2C output contract
(``app.core.models.flow_supervisor_result.FlowSupervisorResult``), not a
reuse of it: Stage 2C aggregates a 1-D matrix (analyst type only) anchored to
``windows: tuple[AnalyticsWindow, ...]``, while Stage 3C aggregates a genuine
2-D matrix (analyst type x timeframe) with no ``AnalyticsWindow`` concept at
all - forcing reuse would fake one axis or the other for no benefit.

Every embedded ``TechnicalAnalysisResult`` is carried unchanged: the
Supervisor never re-grades, re-derives or launders Stage 3B evidence/quality
- it only counts, tallies and cross-references what Stage 3B already
produced. No new ``TechnicalEvidence`` is ever minted here; every coherence
evidence reference is a ``(result_index, observation_index)`` pair pointing
into the canonically ordered ``analyst_results`` tuple, mirroring
``FlowSupervisorResult.relationship_evidence_refs`` one contour over, so the
whole reference chain survives serialization without any external lookup.

This model can structurally never carry a ``TradeDirection``, a score, a
weight, a timeframe/analyst confidence, or a free-text market verdict.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAgreementVerdict, TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.enums.technical_supervisor import TechnicalSupervisorOutcome
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.technical_analysis_result import TechnicalAnalysisResult

Cell = tuple[TechnicalAnalystType, Timeframe]


class TechnicalCoherenceResult(DomainModel):
    """One cross-timeframe categorical tally for a single, genuinely
    comparable ``(dimension, subject)`` group.

    ``subject`` mirrors ``TechnicalAnalysisObservation.subject`` verbatim
    (e.g. a moving-average period or period-pair identity) so period-specific
    dimensions are never conflated across periods; it is ``None`` for every
    dimension that is not period-scoped.
    """

    dimension: TechnicalAnalysisDimension
    subject: str | None = None
    verdict: TechnicalAgreementVerdict
    contributing_timeframes: tuple[Timeframe, ...] = Field(default_factory=tuple)
    evidence_refs: tuple[tuple[int, int], ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_verdict_consistency(self) -> Self:
        if self.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA:
            if self.contributing_timeframes:
                raise ValueError("INSUFFICIENT_DATA coherence must not carry contributing_timeframes")
            if self.evidence_refs:
                raise ValueError("INSUFFICIENT_DATA coherence must not carry evidence_refs")
        else:
            if len(self.contributing_timeframes) < 2:
                raise ValueError("ALL_AGREE/MIXED coherence must carry at least 2 contributing timeframes")
            if len(set(self.contributing_timeframes)) != len(self.contributing_timeframes):
                raise ValueError("contributing_timeframes must not contain duplicates")
            if len(self.evidence_refs) != len(self.contributing_timeframes):
                raise ValueError("evidence_refs must carry exactly one entry per contributing timeframe")
        return self


class TechnicalTimeframeSummary(DomainModel):
    """Availability/coverage/quality summary for one expected timeframe
    across every expected analyst. Carries no direction, score, weight or
    trading recommendation of any kind."""

    timeframe: Timeframe
    analyzed_analysts: tuple[TechnicalAnalystType, ...] = Field(default_factory=tuple)
    abstained_analysts: tuple[TechnicalAnalystType, ...] = Field(default_factory=tuple)
    missing_analysts: tuple[TechnicalAnalystType, ...] = Field(default_factory=tuple)
    analyzed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    usable_ratio: float = Field(ge=0.0, le=1.0)
    quality: FeatureQuality

    @model_validator(mode="after")
    def _validate_partition(self) -> Self:
        analyzed = set(self.analyzed_analysts)
        abstained = set(self.abstained_analysts)
        missing = set(self.missing_analysts)
        for name, bucket, bucket_set in (
            ("analyzed_analysts", self.analyzed_analysts, analyzed),
            ("abstained_analysts", self.abstained_analysts, abstained),
            ("missing_analysts", self.missing_analysts, missing),
        ):
            if len(bucket_set) != len(bucket):
                raise ValueError(f"{name} must not contain duplicates")
        if not analyzed.isdisjoint(abstained) or not analyzed.isdisjoint(missing) or not abstained.isdisjoint(missing):
            raise ValueError("an analyst type must belong to exactly one participation bucket")
        return self

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.analyzed_count != len(self.analyzed_analysts):
            raise ValueError("analyzed_count must equal len(analyzed_analysts)")
        if self.abstained_count != len(self.abstained_analysts):
            raise ValueError("abstained_count must equal len(abstained_analysts)")
        if self.missing_count != len(self.missing_analysts):
            raise ValueError("missing_count must equal len(missing_analysts)")
        total = self.analyzed_count + self.abstained_count + self.missing_count
        if total == 0:
            raise ValueError("a timeframe summary must cover at least one analyst")
        expected_ratio = self.analyzed_count / total
        if abs(self.usable_ratio - expected_ratio) > 1e-9:
            raise ValueError("usable_ratio must equal analyzed_count / (analyzed+abstained+missing)")
        return self


class TechnicalAnalystSummary(DomainModel):
    """Availability/coverage/quality summary for one expected analyst
    across every expected timeframe. Carries no direction, score, weight or
    trading recommendation of any kind."""

    analyst_type: TechnicalAnalystType
    analyzed_timeframes: tuple[Timeframe, ...] = Field(default_factory=tuple)
    abstained_timeframes: tuple[Timeframe, ...] = Field(default_factory=tuple)
    missing_timeframes: tuple[Timeframe, ...] = Field(default_factory=tuple)
    analyzed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    usable_ratio: float = Field(ge=0.0, le=1.0)
    quality: FeatureQuality

    @model_validator(mode="after")
    def _validate_partition(self) -> Self:
        analyzed = set(self.analyzed_timeframes)
        abstained = set(self.abstained_timeframes)
        missing = set(self.missing_timeframes)
        for name, bucket, bucket_set in (
            ("analyzed_timeframes", self.analyzed_timeframes, analyzed),
            ("abstained_timeframes", self.abstained_timeframes, abstained),
            ("missing_timeframes", self.missing_timeframes, missing),
        ):
            if len(bucket_set) != len(bucket):
                raise ValueError(f"{name} must not contain duplicates")
        if not analyzed.isdisjoint(abstained) or not analyzed.isdisjoint(missing) or not abstained.isdisjoint(missing):
            raise ValueError("a timeframe must belong to exactly one participation bucket")
        return self

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.analyzed_count != len(self.analyzed_timeframes):
            raise ValueError("analyzed_count must equal len(analyzed_timeframes)")
        if self.abstained_count != len(self.abstained_timeframes):
            raise ValueError("abstained_count must equal len(abstained_timeframes)")
        if self.missing_count != len(self.missing_timeframes):
            raise ValueError("missing_count must equal len(missing_timeframes)")
        total = self.analyzed_count + self.abstained_count + self.missing_count
        if total == 0:
            raise ValueError("an analyst summary must cover at least one timeframe")
        expected_ratio = self.analyzed_count / total
        if abs(self.usable_ratio - expected_ratio) > 1e-9:
            raise ValueError("usable_ratio must equal analyzed_count / (analyzed+abstained+missing)")
        return self


class TechnicalSupervisorResult(DomainModel):
    """Deterministic aggregation of one evaluation's Stage 3B analyst
    results across the expected analyst x timeframe matrix."""

    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp

    outcome: TechnicalSupervisorOutcome

    expected_analysts: tuple[TechnicalAnalystType, ...] = Field(min_length=1)
    expected_timeframes: tuple[Timeframe, ...] = Field(min_length=1)

    analyzed_cells: tuple[Cell, ...] = Field(default_factory=tuple)
    abstained_cells: tuple[Cell, ...] = Field(default_factory=tuple)
    missing_cells: tuple[Cell, ...] = Field(default_factory=tuple)

    expected_count: int = Field(ge=1)
    analyzed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    usable_cell_ratio: float = Field(ge=0.0, le=1.0)

    overall_quality: FeatureQuality

    per_timeframe_summaries: tuple[TechnicalTimeframeSummary, ...] = Field(default_factory=tuple)
    per_analyst_summaries: tuple[TechnicalAnalystSummary, ...] = Field(default_factory=tuple)

    coherence: tuple[TechnicalCoherenceResult, ...] = Field(default_factory=tuple)

    analyst_results: tuple[TechnicalAnalysisResult, ...] = Field(default_factory=tuple)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_expected_unique(self) -> Self:
        if len(set(self.expected_analysts)) != len(self.expected_analysts):
            raise ValueError("expected_analysts must not contain duplicates")
        if len(set(self.expected_timeframes)) != len(self.expected_timeframes):
            raise ValueError("expected_timeframes must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_cells_partition_expected(self) -> Self:
        expected: set[Cell] = {(a, t) for a in self.expected_analysts for t in self.expected_timeframes}
        analyzed = set(self.analyzed_cells)
        abstained = set(self.abstained_cells)
        missing = set(self.missing_cells)

        for name, bucket, bucket_set in (
            ("analyzed_cells", self.analyzed_cells, analyzed),
            ("abstained_cells", self.abstained_cells, abstained),
            ("missing_cells", self.missing_cells, missing),
        ):
            if len(bucket_set) != len(bucket):
                raise ValueError(f"{name} must not contain duplicates")

        if not analyzed.isdisjoint(abstained) or not analyzed.isdisjoint(missing) or not abstained.isdisjoint(missing):
            raise ValueError("a cell must belong to exactly one participation bucket")

        if (analyzed | abstained | missing) != expected:
            raise ValueError("analyzed/abstained/missing cells must exactly partition the expected matrix")

        return self

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.expected_count != len(self.expected_analysts) * len(self.expected_timeframes):
            raise ValueError("expected_count must equal len(expected_analysts) * len(expected_timeframes)")
        if self.analyzed_count != len(self.analyzed_cells):
            raise ValueError("analyzed_count must equal len(analyzed_cells)")
        if self.abstained_count != len(self.abstained_cells):
            raise ValueError("abstained_count must equal len(abstained_cells)")
        if self.missing_count != len(self.missing_cells):
            raise ValueError("missing_count must equal len(missing_cells)")
        expected_ratio = self.analyzed_count / self.expected_count
        if abs(self.usable_cell_ratio - expected_ratio) > 1e-9:
            raise ValueError("usable_cell_ratio must equal analyzed_count / expected_count")
        return self

    @model_validator(mode="after")
    def _validate_analyst_results(self) -> Self:
        analyzed = set(self.analyzed_cells)
        abstained = set(self.abstained_cells)
        seen_keys: set[Cell] = set()

        for result in self.analyst_results:
            key = (result.analyst_type, result.timeframe)
            if key in seen_keys:
                raise ValueError(f"duplicate analyst_result for {key}")
            seen_keys.add(key)

            if key not in analyzed and key not in abstained:
                raise ValueError(f"analyst_result {key} is neither analyzed nor abstained")
            if result.symbol != self.symbol or result.contract_type != self.contract_type:
                raise ValueError(f"analyst_result {key} symbol/contract_type mismatch")
            if result.observation_time != self.observation_time:
                raise ValueError(f"analyst_result {key} observation_time mismatch")

            expected_status = TechnicalAnalystOutcome.ANALYZED if key in analyzed else TechnicalAnalystOutcome.ABSTAINED
            if result.status is not expected_status:
                raise ValueError(f"analyst_result {key} status does not match participation bucket")

        if seen_keys != (analyzed | abstained):
            raise ValueError("analyst_results must exactly match analyzed+abstained cells")

        return self

    @model_validator(mode="after")
    def _validate_coherence_no_duplicate_groups(self) -> Self:
        keys = [(c.dimension, c.subject) for c in self.coherence]
        if len(set(keys)) != len(keys):
            raise ValueError("coherence must not contain duplicate (dimension, subject) groups")
        return self

    @model_validator(mode="after")
    def _validate_coherence_evidence_refs(self) -> Self:
        for coherence in self.coherence:
            referenced_timeframes: list[Timeframe] = []
            for result_idx, observation_idx in coherence.evidence_refs:
                if result_idx < 0 or result_idx >= len(self.analyst_results):
                    raise ValueError(f"coherence evidence_refs references invalid result index {result_idx}")
                result = self.analyst_results[result_idx]
                observations = result.observations
                if observation_idx < 0 or observation_idx >= len(observations):
                    raise ValueError(
                        f"coherence evidence_refs references invalid observation index {observation_idx} "
                        f"for result index {result_idx}"
                    )
                observation = observations[observation_idx]
                if observation.dimension is not coherence.dimension:
                    raise ValueError(
                        f"coherence evidence_ref ({result_idx}, {observation_idx}) dimension does not match "
                        f"coherence dimension {coherence.dimension}"
                    )
                if observation.subject != coherence.subject:
                    raise ValueError(
                        f"coherence evidence_ref ({result_idx}, {observation_idx}) subject does not match "
                        f"coherence subject {coherence.subject!r}"
                    )
                referenced_timeframes.append(result.timeframe)

            if len(set(referenced_timeframes)) != len(referenced_timeframes):
                raise ValueError(f"coherence {coherence.dimension}/{coherence.subject!r} evidence_refs reference a duplicate timeframe")
            if set(referenced_timeframes) != set(coherence.contributing_timeframes):
                raise ValueError(
                    f"coherence {coherence.dimension}/{coherence.subject!r} evidence_refs timeframes do not match contributing_timeframes"
                )
        return self

    @model_validator(mode="after")
    def _validate_per_timeframe_summaries(self) -> Self:
        expected_timeframe_set = set(self.expected_timeframes)
        seen: set[Timeframe] = set()
        for summary in self.per_timeframe_summaries:
            if summary.timeframe in seen:
                raise ValueError(f"duplicate per_timeframe_summary for {summary.timeframe}")
            seen.add(summary.timeframe)
            if summary.timeframe not in expected_timeframe_set:
                raise ValueError(f"per_timeframe_summary for unexpected timeframe {summary.timeframe}")

            covered = set(summary.analyzed_analysts) | set(summary.abstained_analysts) | set(summary.missing_analysts)
            if covered != set(self.expected_analysts):
                raise ValueError(f"per_timeframe_summary for {summary.timeframe} must cover exactly expected_analysts")

            expected_analyzed = {a for (a, t) in self.analyzed_cells if t == summary.timeframe}
            expected_abstained = {a for (a, t) in self.abstained_cells if t == summary.timeframe}
            expected_missing = {a for (a, t) in self.missing_cells if t == summary.timeframe}
            if set(summary.analyzed_analysts) != expected_analyzed:
                raise ValueError(f"per_timeframe_summary for {summary.timeframe} analyzed_analysts mismatch")
            if set(summary.abstained_analysts) != expected_abstained:
                raise ValueError(f"per_timeframe_summary for {summary.timeframe} abstained_analysts mismatch")
            if set(summary.missing_analysts) != expected_missing:
                raise ValueError(f"per_timeframe_summary for {summary.timeframe} missing_analysts mismatch")

        if self.per_timeframe_summaries and seen != expected_timeframe_set:
            raise ValueError("per_timeframe_summaries must cover exactly expected_timeframes")
        return self

    @model_validator(mode="after")
    def _validate_per_analyst_summaries(self) -> Self:
        expected_analyst_set = set(self.expected_analysts)
        seen: set[TechnicalAnalystType] = set()
        for summary in self.per_analyst_summaries:
            if summary.analyst_type in seen:
                raise ValueError(f"duplicate per_analyst_summary for {summary.analyst_type}")
            seen.add(summary.analyst_type)
            if summary.analyst_type not in expected_analyst_set:
                raise ValueError(f"per_analyst_summary for unexpected analyst {summary.analyst_type}")

            covered = set(summary.analyzed_timeframes) | set(summary.abstained_timeframes) | set(summary.missing_timeframes)
            if covered != set(self.expected_timeframes):
                raise ValueError(f"per_analyst_summary for {summary.analyst_type} must cover exactly expected_timeframes")

            expected_analyzed = {t for (a, t) in self.analyzed_cells if a == summary.analyst_type}
            expected_abstained = {t for (a, t) in self.abstained_cells if a == summary.analyst_type}
            expected_missing = {t for (a, t) in self.missing_cells if a == summary.analyst_type}
            if set(summary.analyzed_timeframes) != expected_analyzed:
                raise ValueError(f"per_analyst_summary for {summary.analyst_type} analyzed_timeframes mismatch")
            if set(summary.abstained_timeframes) != expected_abstained:
                raise ValueError(f"per_analyst_summary for {summary.analyst_type} abstained_timeframes mismatch")
            if set(summary.missing_timeframes) != expected_missing:
                raise ValueError(f"per_analyst_summary for {summary.analyst_type} missing_timeframes mismatch")

        if self.per_analyst_summaries and seen != expected_analyst_set:
            raise ValueError("per_analyst_summaries must cover exactly expected_analysts")
        return self


__all__ = ["TechnicalAnalystSummary", "TechnicalCoherenceResult", "TechnicalSupervisorResult", "TechnicalTimeframeSummary"]
