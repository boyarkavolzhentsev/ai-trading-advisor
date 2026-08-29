"""Stage 6A strategy-router enums - structural eligibility vocabulary only.

No member here encodes a trading direction, a qualitative market judgment,
a dimension/value interpretation, a ranking, a score, or a confidence.
Every value describes either which strategy family a structural eligibility
statement is about, the coarse routing outcome across all families, or an
exact structural reason one family failed eligibility - never what any
contour's evidence *says*. Semantic interpretation of dimension/value
content starts at Stage 6B Judge, never here.
"""

from __future__ import annotations

from enum import StrEnum


class StrategyFamily(StrEnum):
    """Strategy family whose structural evidence readiness Stage 6A evaluates.

    ``TREND_FOLLOWING`` and ``MEAN_REVERSION`` intentionally share an
    identical Router structural eligibility rule in V1 (both require only a
    usable technical contour) - Stage 6A has no structural fact that could
    distinguish a trending market from a ranging one; that distinction is
    Stage 6B Judge's, drawn from dimension/value content this layer never
    reads.
    """

    TREND_FOLLOWING = "TREND_FOLLOWING"
    MEAN_REVERSION = "MEAN_REVERSION"
    BREAKOUT = "BREAKOUT"
    EVENT_DRIVEN = "EVENT_DRIVEN"


class StrategyRouterOutcome(StrEnum):
    """Coarse routing verdict across every ``StrategyFamily``.

    Describes eligibility participation only - never a ranking, a preferred
    strategy, a winner, a score, or a confidence.
    """

    ROUTED = "ROUTED"
    NO_ELIGIBLE_STRATEGY = "NO_ELIGIBLE_STRATEGY"


class StrategyIneligibilityReason(StrEnum):
    """Exact structural reason one strategy family was found ineligible.

    Each member maps to exactly one independently-checked structural fact on
    ``MarketEvaluationResult`` - never a free-text explanation.
    """

    CONTOUR_MISSING = "CONTOUR_MISSING"
    CONTOUR_INSUFFICIENT_EVIDENCE = "CONTOUR_INSUFFICIENT_EVIDENCE"
    QUALITY_UNAVAILABLE = "QUALITY_UNAVAILABLE"
    EXTERNAL_SCOPE_NOT_ALIGNED = "EXTERNAL_SCOPE_NOT_ALIGNED"


__all__ = [
    "StrategyFamily",
    "StrategyIneligibilityReason",
    "StrategyRouterOutcome",
]
