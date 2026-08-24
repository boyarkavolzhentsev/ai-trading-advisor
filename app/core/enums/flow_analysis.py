"""Stage 2B flow-analyst enums - deterministic categorical vocabulary only.

No member here ever means BUY/SELL/LONG/SHORT as a trading instruction (that
vocabulary is ``app.core.enums.trade.TradeDirection``, reserved for later,
genuinely directional agents - see ``app.core.models.assessment.AgentAssessment``).
No member is a magnitude-threshold-derived label (``STRONG``/``WEAK``/
``EXTREME``/``UNUSUAL``/...): Stage 2B v1 classifies only sign, presence, and
structural window/band comparisons already computed by Stage 2A - see
``app.flow_analysts.base`` for the shared primitives that produce these
values.
"""

from __future__ import annotations

from enum import StrEnum


class AnalystType(StrEnum):
    """Identifies which Stage 2B specialist produced a ``FlowAnalysisResult``."""

    TAKER_FLOW = "TAKER_FLOW"
    LIQUIDATION = "LIQUIDATION"
    ORDER_BOOK_LIQUIDITY = "ORDER_BOOK_LIQUIDITY"
    OPEN_INTEREST = "OPEN_INTEREST"
    FUNDING = "FUNDING"
    PRICE_FLOW_RELATIONSHIP = "PRICE_FLOW_RELATIONSHIP"


class AnalystOutcome(StrEnum):
    """Whether an analyst produced observations or abstained outright."""

    ANALYZED = "ANALYZED"
    ABSTAINED = "ABSTAINED"


class AnalysisDimension(StrEnum):
    """What aspect of flow behavior one ``FlowAnalysisObservation`` describes."""

    DIRECTIONAL_PRESSURE = "DIRECTIONAL_PRESSURE"
    ACTIVITY_PRESENCE = "ACTIVITY_PRESENCE"
    PERSISTENCE = "PERSISTENCE"
    CROSS_BAND_AGREEMENT = "CROSS_BAND_AGREEMENT"
    MAGNITUDE_TREND = "MAGNITUDE_TREND"
    DEPTH_TREND = "DEPTH_TREND"
    OPEN_INTEREST_TREND = "OPEN_INTEREST_TREND"
    OPEN_INTEREST_VELOCITY_TREND = "OPEN_INTEREST_VELOCITY_TREND"
    FUNDING_SIGN = "FUNDING_SIGN"
    FUNDING_TREND = "FUNDING_TREND"
    BASIS_SIGN = "BASIS_SIGN"
    CORRELATION_RELATIONSHIP = "CORRELATION_RELATIONSHIP"
    PRICE_TAKER_RELATIONSHIP = "PRICE_TAKER_RELATIONSHIP"
    PRICE_OPEN_INTEREST_RELATIONSHIP = "PRICE_OPEN_INTEREST_RELATIONSHIP"
    PRICE_LIQUIDATION_RELATIONSHIP = "PRICE_LIQUIDATION_RELATIONSHIP"


class AgreementVerdict(StrEnum):
    """Deterministic tally of a categorical value across a comparison set.

    Shared by every "persistence"/"agreement across windows or bands"
    dimension rather than one bespoke enum per analyst - persistence and
    cross-window/cross-band agreement are the identical structural tally
    (do all qualifying entries carry the same category) applied to
    different comparison sets.
    """

    ALL_AGREE = "ALL_AGREE"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class OrdinalTrend(StrEnum):
    """Shortest-vs-longest-window ordinal comparison of one signed magnitude."""

    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TakerFlowPressure(StrEnum):
    """Sign of executed taker delta within one window."""

    BUY_DOMINANT = "BUY_DOMINANT"
    SELL_DOMINANT = "SELL_DOMINANT"
    BALANCED = "BALANCED"


class LiquidationPressure(StrEnum):
    """Sign of forced-liquidation imbalance within one window."""

    LONG_LIQUIDATIONS_DOMINANT = "LONG_LIQUIDATIONS_DOMINANT"
    SHORT_LIQUIDATIONS_DOMINANT = "SHORT_LIQUIDATIONS_DOMINANT"
    BALANCED = "BALANCED"


class LiquidationActivity(StrEnum):
    """Whether any forced liquidation was observed in one window.

    Kept distinct from ``LiquidationPressure``: a healthy window with zero
    liquidation events is a legitimate ``NO_ACTIVITY`` (VALID zero), never
    conflated with ``BALANCED`` (which means events occurred on both sides
    in equal volume).
    """

    ACTIVITY_PRESENT = "ACTIVITY_PRESENT"
    NO_ACTIVITY = "NO_ACTIVITY"


class OrderBookPressure(StrEnum):
    """Sign of order-book depth imbalance within one band."""

    BID_HEAVIER = "BID_HEAVIER"
    ASK_HEAVIER = "ASK_HEAVIER"
    BALANCED = "BALANCED"


class DepthTrend(StrEnum):
    """Sign of one book side's depth change across one window."""

    THICKENING = "THICKENING"
    THINNING = "THINNING"
    UNCHANGED = "UNCHANGED"


class OpenInterestTrend(StrEnum):
    """Sign of an open-interest change quantity (percent change or velocity)."""

    EXPANDING = "EXPANDING"
    CONTRACTING = "CONTRACTING"
    FLAT = "FLAT"


class FundingSign(StrEnum):
    """Sign of the latest funding rate."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ZERO = "ZERO"


class FundingTrend(StrEnum):
    """Sign of funding-rate trend within one window."""

    RISING = "RISING"
    FALLING = "FALLING"
    FLAT = "FLAT"


class BasisSign(StrEnum):
    """Sign of the mark/index price basis."""

    MARK_ABOVE_INDEX = "MARK_ABOVE_INDEX"
    MARK_BELOW_INDEX = "MARK_BELOW_INDEX"
    AT_PARITY = "AT_PARITY"


class CorrelationRelationship(StrEnum):
    """Sign of an already-computed Stage 2A cross-feature correlation."""

    POSITIVE_RELATIONSHIP = "POSITIVE_RELATIONSHIP"
    NEGATIVE_RELATIONSHIP = "NEGATIVE_RELATIONSHIP"
    NO_RELATIONSHIP = "NO_RELATIONSHIP"


class PriceFlowRelationship(StrEnum):
    """Instantaneous sign relationship between price return and one flow metric.

    ``NO_DIRECTION`` is the explicit, conservative zero case: whenever either
    side of the comparison is exactly zero, the relationship is reported as
    having no direction rather than being guessed as agreement or divergence.
    """

    AGREEMENT = "AGREEMENT"
    DIVERGENCE = "DIVERGENCE"
    NO_DIRECTION = "NO_DIRECTION"


__all__ = [
    "AgreementVerdict",
    "AnalysisDimension",
    "AnalystOutcome",
    "AnalystType",
    "BasisSign",
    "CorrelationRelationship",
    "DepthTrend",
    "FundingSign",
    "FundingTrend",
    "LiquidationActivity",
    "LiquidationPressure",
    "OpenInterestTrend",
    "OrdinalTrend",
    "OrderBookPressure",
    "PriceFlowRelationship",
    "TakerFlowPressure",
]
