"""Deterministic evidence contract backing every Stage 4F analyst observation.

Every ``ExternalIntelligenceAnalysisObservation``
(``app.core.models.external_intelligence_analysis_result``) cites at least
one ``ExternalIntelligenceEvidence`` entry so a future Stage 4G supervisor
can inspect *why* an analyst reached a conclusion - no opaque free-text-only
output, mirroring ``FlowEvidence``/``TechnicalEvidence``. Values are
stringified rather than typed as a ``Decimal | float | int`` union so the
record stays uniform and trivially auditable/serializable; evidence is for
audit, not further arithmetic.

Extends ``FlowEvidence``/``TechnicalEvidence``'s shape with three fields
neither sibling needed: ``source_provider``, ``source_record_id`` and
``source_received_at``. Flow/Technical evidence only ever cites an
in-process Stage 2A/3A feature block with no independent persisted
identity; Stage 4F evidence must trace back to one specific, persisted
Stage 4A-4E fact by its own ``(provider, provider_record_id)`` identity and
retained ``received_at`` version marker.

``source_timestamp`` is always the underlying fact's *semantic* time
(``EconomicEvent.event_time`` / ``*Observation.observation_time`` /
``NewsItem.published_at`` - never ``received_at``) - see the Stage 4F
design review: staleness is classified from this field, never from
``source_received_at``. ``source_received_at`` is retained purely as
ingestion/audit/version-traceability metadata and never drives any
deterministic classification in this package.

``source_record_id`` carries whichever provider-native identifier applies
to the cited fact's own foundation (``provider_event_id`` for macro,
``provider_series_id`` for rates/on-chain, ``provider_item_id`` for news) -
one field name across heterogeneous foundations, not a separate Evidence
model per analyst family, since the identifier is always a single opaque
provider-native string regardless of which foundation it came from.

A calculation involving two source facts (a trend, a slope, a surprise)
always cites **two** evidence entries, one per fact - never one entry
bundling both.
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel, Timestamp


class ExternalIntelligenceEvidence(DomainModel):
    """One traceable, already-computed Stage 4A-4E fact backing an observation."""

    feature_name: str = Field(min_length=1)
    observed_value: str = Field(min_length=1)
    reference_value: str | None = None
    quality: FeatureQuality
    source_timestamp: Timestamp
    source_provider: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_received_at: Timestamp
    provenance: str = Field(min_length=1)


__all__ = ["ExternalIntelligenceEvidence"]
