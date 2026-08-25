"""Shared ``FeatureStatus``-building helpers for Stage 3A.

Judge, never repair: every helper here only classifies already-computed
inputs into a verdict; none of them mutate, fill in or invent data.

Deliberately independent of ``app.flow.quality``: Stage 3A must remain an
independently testable contour with no import edge into ``app.flow``. This
module is a narrow, intentional duplication of the same tiny verdict-
building shape used one contour over - not a shared dependency. A future
change may promote both copies to one shared ``app.core`` location once both
contours are stable; that refactor is explicitly out of scope here.
"""

from __future__ import annotations

from collections.abc import Iterable

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
    """
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def worse_of_many(qualities: Iterable[FeatureQuality]) -> FeatureQuality:
    """Fold :func:`worse_of` over an iterable of qualities.

    The caller must not invoke this with an empty iterable when no quality
    was actually consulted - there is no meaningful "no quality" fallback.
    """
    result = FeatureQuality.VALID
    for quality in qualities:
        result = worse_of(result, quality)
    return result


__all__ = ["partial", "stale", "unavailable", "valid", "worse_of", "worse_of_many"]
