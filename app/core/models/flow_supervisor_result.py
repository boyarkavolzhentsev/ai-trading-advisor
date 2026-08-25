"""Stage 2C deterministic flow-supervisor output contract.

Aggregates already-produced Stage 2B ``FlowAnalysisResult`` objects for one
snapshot. Deliberately separate from any future ``Judge``/``AgentAssessment``
contract (``app.core.models.assessment``): this model describes analyst
participation, evidence coverage/quality, and the one place cross-domain
comparison is genuinely safe (price/flow relationship agreement) - it can
structurally never carry a ``TradeDirection``, a score, a weight, or a
free-text market verdict.

Every embedded ``FlowAnalysisResult`` is carried unchanged: the Supervisor
never re-grades, re-derives or launders Stage 2B evidence/quality - it only
counts, tallies and cross-references what Stage 2B already produced. No new
``FlowEvidence`` is ever minted here; ``relationship_evidence_refs`` points
into the embedded results the same way a ``FlowAnalysisObservation`` points
into its own result's ``evidence`` tuple (see
``app.core.models.flow_analysis_result``), so the whole reference chain
survives serialization without any external lookup.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.flow_analysis import AgreementVerdict, AnalystOutcome, AnalystType
from app.core.enums.flow_supervisor import FlowSupervisorOutcome
from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.flow_analysis_result import FlowAnalysisResult


class FlowSupervisorResult(DomainModel):
    """Deterministic aggregation of one snapshot's Stage 2B analyst results."""

    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp
    windows: tuple[AnalyticsWindow, ...]

    outcome: FlowSupervisorOutcome

    expected_analysts: tuple[AnalystType, ...] = Field(min_length=1)
    analyzed_analysts: tuple[AnalystType, ...] = Field(default_factory=tuple)
    abstained_analysts: tuple[AnalystType, ...] = Field(default_factory=tuple)
    missing_analysts: tuple[AnalystType, ...] = Field(default_factory=tuple)

    overall_quality: FeatureQuality

    expected_count: int = Field(ge=1)
    analyzed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    usable_analyst_ratio: float = Field(ge=0.0, le=1.0)

    relationship_coherence: AgreementVerdict
    relationship_evidence_refs: tuple[tuple[int, int], ...] = Field(default_factory=tuple)

    analyst_results: tuple[FlowAnalysisResult, ...] = Field(default_factory=tuple)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_expected_analysts_unique(self) -> Self:
        if len(set(self.expected_analysts)) != len(self.expected_analysts):
            raise ValueError("expected_analysts must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_participation_partitions_expected(self) -> Self:
        expected = set(self.expected_analysts)
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

        if (analyzed | abstained | missing) != expected:
            raise ValueError("analyzed/abstained/missing must exactly partition expected_analysts")

        return self

    @model_validator(mode="after")
    def _validate_counts(self) -> Self:
        if self.expected_count != len(self.expected_analysts):
            raise ValueError("expected_count must equal len(expected_analysts)")
        if self.analyzed_count != len(self.analyzed_analysts):
            raise ValueError("analyzed_count must equal len(analyzed_analysts)")
        if self.abstained_count != len(self.abstained_analysts):
            raise ValueError("abstained_count must equal len(abstained_analysts)")
        if self.missing_count != len(self.missing_analysts):
            raise ValueError("missing_count must equal len(missing_analysts)")
        expected_ratio = self.analyzed_count / self.expected_count
        if abs(self.usable_analyst_ratio - expected_ratio) > 1e-9:
            raise ValueError("usable_analyst_ratio must equal analyzed_count / expected_count")
        return self

    @model_validator(mode="after")
    def _validate_analyst_results(self) -> Self:
        seen_types: set[AnalystType] = set()
        for result in self.analyst_results:
            if result.analyst_type in seen_types:
                raise ValueError(f"duplicate analyst_type {result.analyst_type} in analyst_results")
            seen_types.add(result.analyst_type)

            if result.analyst_type not in self.expected_analysts:
                raise ValueError(f"analyst_type {result.analyst_type} not in expected_analysts")
            if result.symbol != self.symbol or result.contract_type != self.contract_type:
                raise ValueError(f"analyst_result {result.analyst_type} symbol/contract_type mismatch")
            if result.observation_time != self.observation_time:
                raise ValueError(f"analyst_result {result.analyst_type} observation_time mismatch")
            if result.windows != self.windows:
                raise ValueError(f"analyst_result {result.analyst_type} windows mismatch")

            if result.analyst_type in self.analyzed_analysts:
                expected_status = AnalystOutcome.ANALYZED
            elif result.analyst_type in self.abstained_analysts:
                expected_status = AnalystOutcome.ABSTAINED
            else:
                raise ValueError(
                    f"analyst_result {result.analyst_type} is neither analyzed nor abstained"
                )
            if result.status is not expected_status:
                raise ValueError(f"analyst_result {result.analyst_type} status does not match participation bucket")

        if seen_types != (set(self.analyzed_analysts) | set(self.abstained_analysts)):
            raise ValueError("analyst_results must exactly match analyzed+abstained analyst types")

        return self

    @model_validator(mode="after")
    def _validate_relationship_evidence_refs(self) -> Self:
        for analyst_idx, observation_idx in self.relationship_evidence_refs:
            if analyst_idx < 0 or analyst_idx >= len(self.analyst_results):
                raise ValueError(f"relationship_evidence_refs references invalid analyst index {analyst_idx}")
            observations = self.analyst_results[analyst_idx].observations
            if observation_idx < 0 or observation_idx >= len(observations):
                raise ValueError(
                    f"relationship_evidence_refs references invalid observation index {observation_idx} "
                    f"for analyst index {analyst_idx}"
                )
        return self

    @model_validator(mode="after")
    def _validate_relationship_refs_match_coherence(self) -> Self:
        if self.relationship_coherence is AgreementVerdict.INSUFFICIENT_DATA:
            if self.relationship_evidence_refs:
                raise ValueError("INSUFFICIENT_DATA relationship_coherence must not carry evidence refs")
        elif not self.relationship_evidence_refs:
            raise ValueError("ALL_AGREE/MIXED relationship_coherence must carry evidence refs")
        return self


__all__ = ["FlowSupervisorResult"]
