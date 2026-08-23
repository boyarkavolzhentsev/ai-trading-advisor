"""Deterministic numeric cross-feature co-movement calculator.

Deliberately minimal: a plain Pearson correlation coefficient between two
already-computed, caller-supplied numeric series - never a
"divergence"/"confirmation"/bullish-bearish label. Any pairing beyond
correlation (bursts, regime labels, etc.) is out of scope for this
deterministic layer.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.flow.quality import unavailable, valid

MIN_SAMPLES_FOR_CORRELATION = 3


def compute_cross_feature_observation(
    *,
    symbol: str,
    contract_type: ContractType,
    window: AnalyticsWindow,
    pair_label: str,
    series_a: Sequence[float | None],
    series_b: Sequence[float | None],
) -> CrossFeatureObservation:
    """Compute the Pearson correlation of two aligned, possibly-partial series.

    Samples where either value is ``None`` are dropped before correlating;
    ``series_a``/``series_b`` must already be pairwise aligned (same index
    means same observation) by the caller.
    """
    paired = [
        (a, b) for a, b in zip(series_a, series_b, strict=True) if a is not None and b is not None
    ]

    if len(paired) < MIN_SAMPLES_FOR_CORRELATION:
        return CrossFeatureObservation(
            symbol=symbol,
            contract_type=contract_type,
            window=window,
            pair_label=pair_label,
            sample_count=len(paired),
            status=unavailable(
                f"fewer than {MIN_SAMPLES_FOR_CORRELATION} paired samples", sample_count=len(paired)
            ),
        )

    xs = [pair[0] for pair in paired]
    ys = [pair[1] for pair in paired]
    try:
        correlation = statistics.correlation(xs, ys)
    except statistics.StatisticsError as exc:
        return CrossFeatureObservation(
            symbol=symbol,
            contract_type=contract_type,
            window=window,
            pair_label=pair_label,
            sample_count=len(paired),
            status=unavailable(f"correlation undefined: {exc}", sample_count=len(paired)),
        )

    return CrossFeatureObservation(
        symbol=symbol,
        contract_type=contract_type,
        window=window,
        pair_label=pair_label,
        correlation=correlation,
        sample_count=len(paired),
        status=valid(len(paired)),
    )


__all__ = ["MIN_SAMPLES_FOR_CORRELATION", "compute_cross_feature_observation"]
