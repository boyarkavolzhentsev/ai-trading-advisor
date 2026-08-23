"""Shared ``FeatureStatus``-building helpers.

Judge, never repair: every helper here only classifies already-computed
inputs into a verdict; none of them mutate, fill in or invent data. Mirrors
``DataQualityValidator``'s stance one layer up.
"""

from __future__ import annotations

from datetime import datetime

from app.core.enums.quality import FeatureQuality
from app.core.models.feature_status import FeatureStatus


def valid(sample_count: int) -> FeatureStatus:
    return FeatureStatus(quality=FeatureQuality.VALID, sample_count=sample_count)


def unavailable(reason: str, *, sample_count: int = 0) -> FeatureStatus:
    return FeatureStatus(quality=FeatureQuality.UNAVAILABLE, sample_count=sample_count, reasons=[reason])


def partial(reason: str, *, sample_count: int) -> FeatureStatus:
    return FeatureStatus(quality=FeatureQuality.PARTIAL, sample_count=sample_count, reasons=[reason])


def stale(reason: str, *, sample_count: int) -> FeatureStatus:
    return FeatureStatus(quality=FeatureQuality.STALE, sample_count=sample_count, reasons=[reason])


_SEVERITY: dict[FeatureQuality, int] = {
    FeatureQuality.VALID: 0,
    FeatureQuality.PARTIAL: 1,
    FeatureQuality.STALE: 2,
    FeatureQuality.UNAVAILABLE: 3,
}


def worse_of(a: FeatureQuality, b: FeatureQuality) -> FeatureQuality:
    """Return whichever of ``a``/``b`` is the more severe verdict.

    Severity order: ``UNAVAILABLE`` > ``STALE`` > ``PARTIAL`` > ``VALID``.
    Used to combine an independent freshness verdict with an independent
    sufficiency verdict (e.g. order-book staleness vs. insufficient depth
    for a requested band) without ever silently upgrading to a better one.
    """
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def truncation_reason(
    *,
    window_start: datetime,
    earliest_retained: datetime | None,
    dropped_count: int,
) -> str | None:
    """Return a warning if bounded-history eviction may have truncated the
    requested window, else ``None``.

    Purely structural: it only checks whether eviction has already
    progressed past the window's start; it never estimates how much data
    was actually lost.
    """
    if dropped_count <= 0 or earliest_retained is None:
        return None
    if earliest_retained > window_start:
        return (
            f"bounded history has evicted {dropped_count} item(s); oldest retained "
            f"item ({earliest_retained.isoformat()}) is newer than window_start "
            f"({window_start.isoformat()}); window may be truncated"
        )
    return None


__all__ = ["partial", "stale", "truncation_reason", "unavailable", "valid", "worse_of"]
