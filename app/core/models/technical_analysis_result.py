"""Stage 3B structured analyst output contracts.

Deliberately a parallel model family to the Stage 2B analyst-result contract
(``app.core.models.flow_analysis_result``), not a reuse of it: that Stage 2B
model is anchored to ``windows: tuple[AnalyticsWindow, ...]`` (a snapshot may
carry several analytics windows at once), while a ``TechnicalFeatureSnapshot``
is always exactly one ``(symbol, contract_type, timeframe)`` observation.
Forcing reuse would either fake a ``windows`` tuple or couple this contour to
``AnalyticsWindow`` for no benefit - so ``TechnicalAnalysisResult`` carries its
own ``timeframe``/``last_closed_candle_time`` identity instead.

No free-text summary field: every claim is a structured
``TechnicalAnalysisObservation`` citing at least one ``TechnicalEvidence``
entry - no opaque free-text-only outputs, mirroring that same Stage 2B
stance one contour over.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystOutcome, TechnicalAnalystType
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.technical_evidence import TechnicalEvidence


class TechnicalAnalysisObservation(DomainModel):
    """One structured, evidence-backed classification produced by an analyst.

    ``value`` is the ``.value`` of whichever domain-specific ``StrEnum`` the
    producing analyst used (e.g. ``TrendDirection.UPWARD``) - kept as a plain
    string here so this one model can carry every analyst's distinct
    categorical vocabulary without a giant tagged union, mirroring
    ``FlowAnalysisObservation``.
    """

    dimension: TechnicalAnalysisDimension
    value: str = Field(min_length=1)
    quality: FeatureQuality
    subject: str | None = None
    evidence_refs: tuple[int, ...] = Field(min_length=1)


class TechnicalAnalysisResult(DomainModel):
    """Structured interpretation of one ``TechnicalFeatureSnapshot`` by one analyst."""

    analyst_type: TechnicalAnalystType
    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    observation_time: Timestamp
    last_closed_candle_time: Timestamp | None = None
    status: TechnicalAnalystOutcome
    observations: tuple[TechnicalAnalysisObservation, ...] = Field(default_factory=tuple)
    evidence: tuple[TechnicalEvidence, ...] = Field(default_factory=tuple)
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
        if self.status is TechnicalAnalystOutcome.ABSTAINED:
            if self.observations:
                raise ValueError("an ABSTAINED result must not carry observations")
            if not self.abstention_reasons:
                raise ValueError("an ABSTAINED result must carry at least one abstention reason")
            if self.quality is not FeatureQuality.UNAVAILABLE:
                raise ValueError("an ABSTAINED result must have quality UNAVAILABLE")
        elif self.abstention_reasons:
            raise ValueError("an ANALYZED result must not carry abstention reasons")
        return self


__all__ = ["TechnicalAnalysisObservation", "TechnicalAnalysisResult"]
