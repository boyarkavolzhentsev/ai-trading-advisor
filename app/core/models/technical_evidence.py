"""Deterministic evidence contract backing every Stage 3B analyst observation.

Every ``TechnicalAnalysisObservation``
(``app.core.models.technical_analysis_result``) cites at least one
``TechnicalEvidence`` entry so a future Stage 3C Technical Supervisor can
inspect *why* an analyst reached a conclusion - no opaque free-text-only
output. Mirrors ``app.core.models.flow_evidence.FlowEvidence`` one contour
over, minus the ``window`` field: a ``TechnicalFeatureSnapshot`` is single-
timeframe, so there is no per-evidence window to record (the timeframe is
already carried on the owning ``TechnicalAnalysisResult``).
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Timestamp


class TechnicalEvidence(DomainModel):
    """One traceable, already-computed Stage 3A fact backing an observation."""

    feature_name: str = Field(min_length=1)
    observed_value: str = Field(min_length=1)
    reference_value: str | None = None
    quality: FeatureQuality
    source_timestamp: Timestamp
    provenance: str = Field(min_length=1)


__all__ = ["TechnicalEvidence"]
