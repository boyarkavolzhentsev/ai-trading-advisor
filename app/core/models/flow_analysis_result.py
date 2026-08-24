"""Stage 2B structured analyst output contracts.

Deliberately separate from ``AgentAssessment``
(``app.core.models.assessment``): that model bakes in ``TradeDirection``
(LONG/SHORT/NEUTRAL/WAIT) and is reserved for later, genuinely directional
agents. Stage 2B analysts describe market-flow conditions only - never a
trading direction - so they get their own model family that structurally
cannot carry a ``TradeDirection``.

No free-text summary field: every claim is a structured
``FlowAnalysisObservation`` citing at least one ``FlowEvidence`` entry - no
opaque free-text-only outputs. Human-readable rendering is deferred to a
later stage that consumes this contract, never authored here.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType
from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.flow_evidence import FlowEvidence


class FlowAnalysisObservation(DomainModel):
    """One structured, evidence-backed classification produced by an analyst.

    ``value`` is the ``.value`` of whichever domain-specific ``StrEnum`` the
    producing analyst used (e.g. ``TakerFlowPressure.BUY_DOMINANT``) - kept
    as a plain string here so this one model can carry every analyst's
    distinct categorical vocabulary without a giant tagged union.
    """

    dimension: AnalysisDimension
    value: str = Field(min_length=1)
    quality: FeatureQuality
    window: str | None = None
    subject: str | None = None
    evidence_refs: tuple[int, ...] = Field(min_length=1)


class FlowAnalysisResult(DomainModel):
    """Structured interpretation of one ``FlowFeatureSnapshot`` by one analyst."""

    analyst_type: AnalystType
    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp
    windows: tuple[AnalyticsWindow, ...]
    status: AnalystOutcome
    observations: tuple[FlowAnalysisObservation, ...] = Field(default_factory=tuple)
    evidence: tuple[FlowEvidence, ...] = Field(default_factory=tuple)
    quality: FeatureQuality
    abstention_reasons: tuple[str, ...] = Field(default_factory=tuple)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence_refs(self) -> Self:
        evidence_count = len(self.evidence)
        for observation in self.observations:
            for ref in observation.evidence_refs:
                if ref < 0 or ref >= evidence_count:
                    raise ValueError(
                        f"observation {observation.dimension} references invalid evidence index {ref}"
                    )
        return self

    @model_validator(mode="after")
    def _validate_abstention_consistency(self) -> Self:
        if self.status is AnalystOutcome.ABSTAINED:
            if self.observations:
                raise ValueError("an ABSTAINED result must not carry observations")
            if not self.abstention_reasons:
                raise ValueError("an ABSTAINED result must carry at least one abstention reason")
            if self.quality is not FeatureQuality.UNAVAILABLE:
                raise ValueError("an ABSTAINED result must have quality UNAVAILABLE")
        elif self.abstention_reasons:
            raise ValueError("an ANALYZED result must not carry abstention reasons")
        return self


__all__ = ["FlowAnalysisObservation", "FlowAnalysisResult"]
