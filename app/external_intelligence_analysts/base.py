"""Shared deterministic primitives for Stage 4F analysts.

Reimplemented here, not imported from ``app.flow_analysts.base`` or
``app.technical_analysts.base``: each contour reimplements its own tiny
helper module rather than sharing one across contour boundaries - the same
independence-over-DRY stance those two modules already establish between
each other. Every helper here only classifies or compares already-computed
inputs; none of them read a wall clock, generate randomness, or mutate
anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import TypeVar

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Timestamp
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence

E = TypeVar("E")

_SEVERITY: dict[FeatureQuality, int] = {
    FeatureQuality.VALID: 0,
    FeatureQuality.PARTIAL: 1,
    FeatureQuality.STALE: 2,
    FeatureQuality.UNAVAILABLE: 3,
}
"""Mirrors ``app.flow.quality``'s severity order exactly, for consistency
with the repository-wide ``FeatureQuality`` fold - Stage 4F V1 never
produces a ``PARTIAL`` value itself, but the fold must still order the full
enum correctly in case a future reviewed increment introduces one."""


def sign_category(value: object, *, positive: E, negative: E, zero: E) -> E | None:
    """Classify a signed numeric value into a caller-supplied 3-way category.

    Returns ``None`` (never a fabricated category) when ``value`` is
    ``None``. A genuine zero always maps to ``zero`` - it is never conflated
    with a missing value.
    """
    if value is None:
        return None
    if value > 0:  # type: ignore[operator]
        return positive
    if value < 0:  # type: ignore[operator]
        return negative
    return zero


def agreement_of(values: Sequence[object], *, all_agree: E, mixed: E, insufficient_data: E) -> E:
    """Tally already-qualifying categorical values into a shared verdict.

    Requires at least 2 entries to be meaningful; the caller must already
    have filtered out ambiguous/missing entries - "no value" is never
    treated as (dis)agreement.
    """
    if len(values) < 2:
        return insufficient_data
    return all_agree if len(set(values)) == 1 else mixed


def worse_of(a: FeatureQuality, b: FeatureQuality) -> FeatureQuality:
    """Return whichever of ``a``/``b`` is the more severe verdict."""
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def worse_of_many(qualities: Sequence[FeatureQuality]) -> FeatureQuality:
    """Fold ``worse_of`` over a non-empty sequence of qualities.

    The caller must not invoke this with an empty sequence when no data was
    actually consulted - there is no meaningful "no quality" fallback.
    """
    result = FeatureQuality.VALID
    for quality in qualities:
        result = worse_of(result, quality)
    return result


def classify_quality(source_time: Timestamp, analysis_time: Timestamp, staleness_threshold: timedelta) -> FeatureQuality:
    """Classify one fact's freshness from its own *semantic* source time, never ``received_at``.

    ``age = analysis_time - source_time``. ``age <= staleness_threshold`` ->
    ``VALID``; otherwise ``STALE``. A ``source_time`` in the future relative
    to ``analysis_time`` yields a *negative* age, which is always
    ``<= staleness_threshold`` (a non-negative duration) - so a future
    source time is always ``VALID``, never ``STALE``. This is a deliberate,
    tested choice, not an accidental side effect: staleness is strictly a
    "too old" condition, never a "too new" one - a scheduled future macro
    event, for instance, is never stale merely for not having happened yet.

    Never returns ``UNAVAILABLE`` or ``PARTIAL``: when a fact required for a
    calculation is missing entirely, the caller skips producing that
    observation rather than calling this helper at all - see the Stage 4F
    design report, "Missing-data behavior".
    """
    age = analysis_time - source_time
    if age <= staleness_threshold:
        return FeatureQuality.VALID
    return FeatureQuality.STALE


def make_evidence(
    *,
    feature_name: str,
    observed_value: object,
    reference_value: object | None,
    quality: FeatureQuality,
    source_timestamp: Timestamp,
    source_provider: str,
    source_record_id: str,
    source_received_at: Timestamp,
    provenance: str,
) -> ExternalIntelligenceEvidence:
    """Build one traceable ``ExternalIntelligenceEvidence`` entry from an already-computed value."""
    return ExternalIntelligenceEvidence(
        feature_name=feature_name,
        observed_value=str(observed_value),
        reference_value=str(reference_value) if reference_value is not None else None,
        quality=quality,
        source_timestamp=source_timestamp,
        source_provider=source_provider,
        source_record_id=source_record_id,
        source_received_at=source_received_at,
        provenance=provenance,
    )


def abstain(
    analyst_type: ExternalIntelligenceAnalystType,
    *,
    analysis_time: Timestamp,
    reason: str,
    currency: str | None = None,
    symbol: str | None = None,
    asset: str | None = None,
    network: str | None = None,
) -> ExternalIntelligenceAnalysisResult:
    """Build a scope-appropriate ``ABSTAINED`` result."""
    return ExternalIntelligenceAnalysisResult(
        analyst_type=analyst_type,
        currency=currency,
        symbol=symbol,
        asset=asset,
        network=network,
        analysis_time=analysis_time,
        status=ExternalIntelligenceOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=(reason,),
    )


__all__ = [
    "abstain",
    "agreement_of",
    "classify_quality",
    "make_evidence",
    "sign_category",
    "worse_of",
    "worse_of_many",
]
