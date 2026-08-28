"""Stage 4F analyst configuration.

One small, immutable, analyst-specific config model per analyst that
genuinely needs a threshold - not one giant shared configuration object, and
not a config model handed to an analyst with nothing to configure. No field
carries a silent default: every threshold must be an explicit, reviewable
value the caller supplies, never a magic number embedded in analyst logic.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.models.base import DomainModel


class MacroAnalystConfig(DomainModel):
    """Explicit thresholds for ``MacroEventAnalyst``."""

    proximity_window: timedelta
    staleness_threshold: timedelta


class RatesYieldAnalystConfig(DomainModel):
    """Explicit thresholds for ``RatesYieldAnalyst``.

    Every Rates/Yield dimension is an exact-zero-boundary sign comparison -
    no materiality/flat threshold exists, mirroring
    ``app.flow_analysts``'s own zero-threshold ``FundingTrend``/
    ``OpenInterestTrend`` precedent. Only staleness classification needs an
    explicit value.
    """

    staleness_threshold: timedelta


class NewsSentimentAnalystConfig(DomainModel):
    """Explicit thresholds for ``NewsSentimentAnalyst``.

    ``recency_window`` gates which relevant items are eligible to
    contribute to sentiment aggregation at all; ``staleness_threshold``
    independently grades the ``FeatureQuality`` of whichever evidence *is*
    included - the two serve different purposes and are not collapsed into
    one value.
    """

    recency_window: timedelta
    staleness_threshold: timedelta


class OnChainAnalystConfig(DomainModel):
    """Explicit thresholds for ``OnChainAnalyst``."""

    staleness_threshold: timedelta


__all__ = [
    "MacroAnalystConfig",
    "NewsSentimentAnalystConfig",
    "OnChainAnalystConfig",
    "RatesYieldAnalystConfig",
]
