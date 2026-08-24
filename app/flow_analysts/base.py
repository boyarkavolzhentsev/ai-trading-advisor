"""Shared deterministic primitives for Stage 2B flow analysts.

Every helper here only classifies or compares already-computed Stage 2A
values - mirrors ``app.flow.quality``'s "judge, never repair" stance one
layer up. No helper aggregates raw events, touches ``app.market_data``, or
picks a magnitude threshold; that is out of scope for Stage 2B v1 by design.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import TypeVar

from app.core.enums.flow_analysis import AgreementVerdict, OrdinalTrend
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import Timestamp
from app.core.models.feature_status import FeatureStatus
from app.core.models.flow_evidence import FlowEvidence
from app.flow.quality import worse_of

Number = Decimal | float
E = TypeVar("E")


def qualifies(status: FeatureStatus) -> bool:
    """Whether a Stage 2A feature block's quality is usable at all.

    ``UNAVAILABLE`` is the only quality that disqualifies a value outright;
    ``PARTIAL``/``STALE`` values are real, previously-computed numbers and
    remain usable, carrying their reduced quality forward into the
    observation that consumes them.
    """
    return status.quality is not FeatureQuality.UNAVAILABLE


def sign_category(value: Number | None, *, positive: E, negative: E, zero: E) -> E | None:
    """Classify a signed value into a caller-supplied 3-way category.

    Returns ``None`` (never a fabricated category) when ``value`` is
    ``None``. A genuine zero always maps to ``zero`` - it is never conflated
    with a missing value.
    """
    if value is None:
        return None
    if value > 0:
        return positive
    if value < 0:
        return negative
    return zero


def agreement_of(values: Sequence[object]) -> AgreementVerdict:
    """Tally already-qualifying categorical values into a shared verdict.

    Requires at least 2 entries to be meaningful; the caller must already
    have filtered out windows/bands with no usable value - "no value" is
    never treated as (dis)agreement.
    """
    if len(values) < 2:
        return AgreementVerdict.INSUFFICIENT_DATA
    return AgreementVerdict.ALL_AGREE if len(set(values)) == 1 else AgreementVerdict.MIXED


def ordinal_trend(shortest: Number | None, longest: Number | None) -> OrdinalTrend:
    """Compare a shortest-window value against a longest-window value.

    ``INCREASING`` when the shortest-window value exceeds the longest-window
    value (recent magnitude higher than the broader window), ``DECREASING``
    for the opposite, ``STABLE`` on exact equality, ``INSUFFICIENT_DATA``
    when either input is ``None``.
    """
    if shortest is None or longest is None:
        return OrdinalTrend.INSUFFICIENT_DATA
    if shortest > longest:
        return OrdinalTrend.INCREASING
    if shortest < longest:
        return OrdinalTrend.DECREASING
    return OrdinalTrend.STABLE


def shortest_and_longest(windows_by_label: dict[str, AnalyticsWindow]) -> tuple[str, str] | None:
    """Return the (shortest, longest) window labels by duration.

    ``None`` when fewer than 2 labels are supplied - ordinal shortest-vs-
    longest comparisons require at least 2 qualifying windows.
    """
    if len(windows_by_label) < 2:
        return None
    ordered = sorted(windows_by_label.items(), key=lambda pair: pair[1].duration)
    return ordered[0][0], ordered[-1][0]


def worse_of_many(qualities: Iterable[FeatureQuality]) -> FeatureQuality:
    """Fold ``app.flow.quality.worse_of`` over an iterable of qualities.

    The caller must not invoke this with an empty iterable when no data was
    actually consulted - there is no meaningful "no quality" fallback.
    """
    result = FeatureQuality.VALID
    for quality in qualities:
        result = worse_of(result, quality)
    return result


def make_evidence(
    *,
    feature_name: str,
    window: str | None,
    observed_value: object,
    reference_value: object | None,
    quality: FeatureQuality,
    source_timestamp: Timestamp,
    provenance: str,
) -> FlowEvidence:
    """Build one traceable ``FlowEvidence`` entry from an already-computed value."""
    return FlowEvidence(
        feature_name=feature_name,
        window=window,
        observed_value=str(observed_value),
        reference_value=str(reference_value) if reference_value is not None else None,
        quality=quality,
        source_timestamp=source_timestamp,
        provenance=provenance,
    )


__all__ = [
    "agreement_of",
    "make_evidence",
    "ordinal_trend",
    "qualifies",
    "shortest_and_longest",
    "sign_category",
    "worse_of_many",
]
