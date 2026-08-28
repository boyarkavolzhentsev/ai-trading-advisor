"""Stage 4F structured analyst output contracts.

One shared family across all four Stage 4F analysts (Macro Event, Rates/
Yield, News/Sentiment, On-Chain) - mirrors ``FlowAnalysisResult`` serving
all six Flow analysts alike, not ``TechnicalAnalysisResult``'s split from
Flow. The deciding factor is the same one that produced the Flow/Technical
split in the first place: whether the identity/scope shape is fixed and
shared. Splitting this family per analyst would duplicate two non-trivial
validators (evidence-ref bounds, abstention consistency) four times for no
benefit, whereas Technical's split avoided *faking* a field (``windows``)
that genuinely didn't apply to it - see the Stage 4F design report,
"Output model recommendation".

Deliberately carries no free-form ``provenance: dict[str, str]`` bag (unlike
``FlowAnalysisResult``/``TechnicalAnalysisResult``): per the Stage 4F review,
traceability belongs entirely in structured ``ExternalIntelligenceEvidence``,
never a generic metadata dict.

No free-text summary field: every claim is a structured
``ExternalIntelligenceAnalysisObservation`` citing at least one
``ExternalIntelligenceEvidence`` entry.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.economic_event import CurrencyCode
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.instrument import Asset

_CURRENCY_SCOPED = (ExternalIntelligenceAnalystType.MACRO_EVENT, ExternalIntelligenceAnalystType.RATES_YIELD)


class ExternalIntelligenceAnalysisObservation(DomainModel):
    """One structured, evidence-backed classification produced by an analyst.

    ``value`` is the ``.value`` of whichever domain-specific ``StrEnum`` the
    producing analyst used - kept as a plain string here so this one model
    can carry every analyst's distinct categorical vocabulary without a
    giant tagged union, mirroring ``FlowAnalysisObservation``.
    """

    dimension: ExternalIntelligenceDimension
    value: str = Field(min_length=1)
    quality: FeatureQuality
    subject: str | None = None
    evidence_refs: tuple[int, ...] = Field(min_length=1)


class ExternalIntelligenceAnalysisResult(DomainModel):
    """Structured interpretation of one scope's Stage 4A-4E facts by one analyst."""

    analyst_type: ExternalIntelligenceAnalystType
    currency: CurrencyCode | None = None
    symbol: Symbol | None = None
    asset: Asset | None = None
    network: str | None = None
    analysis_time: Timestamp
    status: ExternalIntelligenceOutcome
    observations: tuple[ExternalIntelligenceAnalysisObservation, ...] = Field(default_factory=tuple)
    evidence: tuple[ExternalIntelligenceEvidence, ...] = Field(default_factory=tuple)
    quality: FeatureQuality
    abstention_reasons: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_scope_shape(self) -> Self:
        if self.analyst_type in _CURRENCY_SCOPED:
            if self.currency is None:
                raise ValueError(f"{self.analyst_type.value} result requires currency")
            if self.symbol is not None or self.asset is not None or self.network is not None:
                raise ValueError(f"{self.analyst_type.value} result must not carry symbol/asset/network")
        elif self.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
            if self.symbol is None:
                raise ValueError("NEWS_SENTIMENT result requires symbol")
            if self.currency is not None or self.asset is not None or self.network is not None:
                raise ValueError("NEWS_SENTIMENT result must not carry currency/asset/network")
        elif self.analyst_type is ExternalIntelligenceAnalystType.ON_CHAIN:
            if self.asset is None or self.network is None:
                raise ValueError("ON_CHAIN result requires both asset and network")
            if self.currency is not None or self.symbol is not None:
                raise ValueError("ON_CHAIN result must not carry currency/symbol")
        return self

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
        if self.status is ExternalIntelligenceOutcome.ABSTAINED:
            if self.observations:
                raise ValueError("an ABSTAINED result must not carry observations")
            if not self.abstention_reasons:
                raise ValueError("an ABSTAINED result must carry at least one abstention reason")
            if self.quality is not FeatureQuality.UNAVAILABLE:
                raise ValueError("an ABSTAINED result must have quality UNAVAILABLE")
        elif self.abstention_reasons:
            raise ValueError("an ANALYZED result must not carry abstention reasons")
        return self


__all__ = ["ExternalIntelligenceAnalysisObservation", "ExternalIntelligenceAnalysisResult"]
