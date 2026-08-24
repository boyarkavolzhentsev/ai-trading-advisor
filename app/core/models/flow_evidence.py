"""Deterministic evidence contract backing every Stage 2B analyst observation.

Every ``FlowAnalysisObservation`` (``app.core.models.flow_analysis_result``)
cites at least one ``FlowEvidence`` entry so a future Flow Supervisor can
inspect *why* an analyst reached a conclusion - no opaque free-text-only
output. Values are stringified rather than typed as a
``Decimal | float | int`` union so the record stays uniform and trivially
auditable/serializable; evidence is for audit, not further arithmetic
(arithmetic stays in ``app.flow``).
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Timestamp


class FlowEvidence(DomainModel):
    """One traceable, already-computed Stage 2A fact backing an observation."""

    feature_name: str = Field(min_length=1)
    window: str | None = None
    observed_value: str = Field(min_length=1)
    reference_value: str | None = None
    quality: FeatureQuality
    source_timestamp: Timestamp
    provenance: str = Field(min_length=1)


__all__ = ["FlowEvidence"]
