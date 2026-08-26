"""Stage 3B technical-analyst enums - deterministic categorical vocabulary only.

No member here ever means BUY/SELL/LONG/SHORT, BOS/CHoCH, overbought/
oversold, or a magnitude-threshold-derived label (``STRONG``/``WEAK``/
``EXTREME``/``HIGH``/``LOW``): Stage 3B v1 classifies only sign, presence,
and comparisons against a mathematically neutral reference (zero, an exact
midpoint, a ratio of 1, or an exact natural boundary) that Stage 3A already
computed - see ``app.technical_analysts.base`` for the shared primitives
that produce these values.

Deliberately independent of ``app.core.enums.flow_analysis``: a narrow,
intentional duplication of the same ``ANALYZED``/``ABSTAINED`` shape one
contour over, not a shared dependency - mirrors the precedent
``app.technical.quality`` already set for Stage 3A relative to
``app.flow.quality``. A future change may promote the genuinely
contour-neutral members (``TechnicalAgreementVerdict``, ``BoundaryPosition``,
``ReferenceComparison``, ``MidpointRelation``) to one shared ``app.core``
location once both contours are stable; that refactor is out of scope here.

Some members are deliberately SHARED across multiple Stage 3B analysts
(``ReferenceComparison``, ``MidpointRelation``, ``BoundaryPosition``,
``TechnicalAgreementVerdict``) because they are produced by one shared
comparison helper in ``app.technical_analysts.base`` applied to
structurally identical inputs (e.g. "a ratio compared to 1.0"), not because
the domains resemble each other. Every other enum here is deliberately kept
one-per-analyst-domain even where the shape is identical (e.g.
``TrendDirection`` vs ``MovingAverageSlopeDirection`` are both a 3-way sign
of a slope, kept separate), mirroring
``app.core.enums.flow_analysis``'s own precedent of keeping
``TakerFlowPressure``/``LiquidationPressure``/``OrderBookPressure`` separate
despite an identical 3-way shape.
"""

from __future__ import annotations

from enum import StrEnum


class TechnicalAnalystType(StrEnum):
    """Identifies which Stage 3B specialist produced a ``TechnicalAnalysisResult``."""

    TREND = "TREND"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    VOLATILITY = "VOLATILITY"
    MOMENTUM = "MOMENTUM"
    MOVING_AVERAGE = "MOVING_AVERAGE"
    CANDLE_STRUCTURE = "CANDLE_STRUCTURE"
    RANGE_STATE = "RANGE_STATE"


class TechnicalAnalystOutcome(StrEnum):
    """Whether an analyst produced observations or abstained outright."""

    ANALYZED = "ANALYZED"
    ABSTAINED = "ABSTAINED"


class TechnicalAnalysisDimension(StrEnum):
    """What aspect of technical behavior one ``TechnicalAnalysisObservation`` describes."""

    RETURN_DIRECTION = "RETURN_DIRECTION"
    SLOPE_DIRECTION = "SLOPE_DIRECTION"
    STRUCTURAL_SEQUENCE_BALANCE = "STRUCTURAL_SEQUENCE_BALANCE"
    TREND_PRIMITIVE_AGREEMENT = "TREND_PRIMITIVE_AGREEMENT"
    DIRECTIONAL_PERSISTENCE = "DIRECTIONAL_PERSISTENCE"
    LATEST_BREAK_DIRECTION = "LATEST_BREAK_DIRECTION"
    STRUCTURAL_BREAK_PRESENCE = "STRUCTURAL_BREAK_PRESENCE"
    BREAK_SEQUENCE_PATTERN = "BREAK_SEQUENCE_PATTERN"
    RANGE_EXPANSION_REFERENCE = "RANGE_EXPANSION_REFERENCE"
    ROC_SIGN = "ROC_SIGN"
    RSI_MIDPOINT_RELATION = "RSI_MIDPOINT_RELATION"
    MOMENTUM_PRIMITIVE_AGREEMENT = "MOMENTUM_PRIMITIVE_AGREEMENT"
    PRICE_VS_SMA_POSITION = "PRICE_VS_SMA_POSITION"
    MA_SLOPE_DIRECTION = "MA_SLOPE_DIRECTION"
    MULTI_PERIOD_MA_ORDERING = "MULTI_PERIOD_MA_ORDERING"
    RANGE_SIZE_STATE = "RANGE_SIZE_STATE"
    BODY_WICK_DOMINANCE = "BODY_WICK_DOMINANCE"
    WICK_SIDE_COMPARISON = "WICK_SIDE_COMPARISON"
    CLOSE_LOCATION_RELATION = "CLOSE_LOCATION_RELATION"
    NORMALIZED_RANGE_REFERENCE = "NORMALIZED_RANGE_REFERENCE"
    DIRECTIONAL_EFFICIENCY_BOUNDARY = "DIRECTIONAL_EFFICIENCY_BOUNDARY"


class TechnicalAgreementVerdict(StrEnum):
    """Deterministic tally of a categorical value across a comparison set.

    Shared across every dimension that tallies "do the qualifying entries
    carry the same category" - the identical structural tally applied to
    different comparison sets, mirroring
    ``app.core.enums.flow_analysis.AgreementVerdict``.
    """

    ALL_AGREE = "ALL_AGREE"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ReferenceComparison(StrEnum):
    """Comparison of an already-computed ratio against the mathematically
    neutral reference ``1.0`` (the ratio's own unit reference point, e.g.
    "current value equals its own baseline"), not a calibrated threshold."""

    ABOVE_REFERENCE = "ABOVE_REFERENCE"
    BELOW_REFERENCE = "BELOW_REFERENCE"
    AT_REFERENCE = "AT_REFERENCE"


class MidpointRelation(StrEnum):
    """Comparison of an already-computed value against its own natural,
    mathematically neutral midpoint (RSI's 50 on ``[0, 100]``, close-location
    value's 0.5 on ``[0, 1]``) - never a calibrated overbought/oversold cut."""

    ABOVE_MIDPOINT = "ABOVE_MIDPOINT"
    BELOW_MIDPOINT = "BELOW_MIDPOINT"
    AT_MIDPOINT = "AT_MIDPOINT"


class BoundaryPosition(StrEnum):
    """Comparison of an already-computed, naturally-bounded value (e.g. a
    ``[0, 1]`` ratio) against its own exact minimum/maximum - never a
    magnitude-strength label."""

    AT_MINIMUM = "AT_MINIMUM"
    AT_MAXIMUM = "AT_MAXIMUM"
    BETWEEN_BOUNDS = "BETWEEN_BOUNDS"


class TrendDirection(StrEnum):
    """Sign of a Stage 3A trend primitive (return or OLS slope).

    Deliberately not bullish/bearish or UPTREND/DOWNTREND - a directional-
    geometry fact only.
    """

    UPWARD = "UPWARD"
    DOWNWARD = "DOWNWARD"
    FLAT = "FLAT"


class StructuralSequenceBalance(StrEnum):
    """Ordinal comparison of Stage 3A's higher-high/higher-low counts against
    its lower-high/lower-low counts."""

    UPWARD_STRUCTURE = "UPWARD_STRUCTURE"
    DOWNWARD_STRUCTURE = "DOWNWARD_STRUCTURE"
    MIXED_STRUCTURE = "MIXED_STRUCTURE"


class StructuralBreakPresence(StrEnum):
    """Whether any confirmed structural break exists in the current snapshot.

    Kept distinct from ``BreakSequencePattern``: a qualifying snapshot with
    zero breaks is a legitimate ``NO_BREAK_CONFIRMED`` (VALID fact), never
    conflated with an unavailable/insufficient-history verdict.
    """

    BREAK_CONFIRMED = "BREAK_CONFIRMED"
    NO_BREAK_CONFIRMED = "NO_BREAK_CONFIRMED"


class BreakSequencePattern(StrEnum):
    """Direction comparison of the two most recent confirmed structural breaks."""

    REPEATED_DIRECTION = "REPEATED_DIRECTION"
    ALTERNATING = "ALTERNATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ROCSign(StrEnum):
    """Sign of Stage 3A's rate-of-change value."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ZERO = "ZERO"


class PricePositionRelativeToMA(StrEnum):
    """Sign of Stage 3A's close-vs-SMA distance for one configured period."""

    ABOVE_SMA = "ABOVE_SMA"
    BELOW_SMA = "BELOW_SMA"
    AT_SMA = "AT_SMA"


class MovingAverageSlopeDirection(StrEnum):
    """Sign of Stage 3A's moving-average slope for one configured period.

    Kept as its own enum rather than reusing ``TrendDirection`` - mirrors
    ``app.core.enums.flow_analysis``'s precedent of one enum per analyst
    domain even where the underlying shape (sign of a fitted slope) is
    identical to another domain's.
    """

    UPWARD = "UPWARD"
    DOWNWARD = "DOWNWARD"
    FLAT = "FLAT"


class MultiPeriodMAOrdering(StrEnum):
    """Current instantaneous ordering of the fastest vs. slowest configured
    SMA period - never a crossover signal (no comparison across time)."""

    FASTER_ABOVE_SLOWER = "FASTER_ABOVE_SLOWER"
    FASTER_BELOW_SLOWER = "FASTER_BELOW_SLOWER"
    EQUAL = "EQUAL"


class RangeSizeState(StrEnum):
    """Whether the most recent closed candle has zero geometric range."""

    ZERO_RANGE = "ZERO_RANGE"
    NON_ZERO_RANGE = "NON_ZERO_RANGE"


class BodyWickDominance(StrEnum):
    """Ordinal comparison of candle body size against combined wick size."""

    BODY_DOMINANT = "BODY_DOMINANT"
    WICK_DOMINANT = "WICK_DOMINANT"
    EQUAL = "EQUAL"


class WickSideComparison(StrEnum):
    """Ordinal comparison of upper wick size against lower wick size."""

    UPPER_WICK_LARGER = "UPPER_WICK_LARGER"
    LOWER_WICK_LARGER = "LOWER_WICK_LARGER"
    EQUAL = "EQUAL"


__all__ = [
    "BodyWickDominance",
    "BoundaryPosition",
    "BreakSequencePattern",
    "MidpointRelation",
    "MovingAverageSlopeDirection",
    "MultiPeriodMAOrdering",
    "PricePositionRelativeToMA",
    "ROCSign",
    "RangeSizeState",
    "ReferenceComparison",
    "StructuralBreakPresence",
    "StructuralSequenceBalance",
    "TechnicalAgreementVerdict",
    "TechnicalAnalysisDimension",
    "TechnicalAnalystOutcome",
    "TechnicalAnalystType",
    "TrendDirection",
    "WickSideComparison",
]
