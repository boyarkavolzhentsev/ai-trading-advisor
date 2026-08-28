"""Stage 4F external-intelligence analyst enums - deterministic vocabulary only.

No member here encodes a trading direction (BUY/SELL/LONG/SHORT), a
qualitative market judgment (BULLISH/BEARISH/RISK_ON/RISK_OFF), or a
magnitude-threshold-derived label (STRONG/WEAK/EXTREME/UNUSUAL) - mirrors
``app.core.enums.flow_analysis``'s discipline exactly. Every member below is
either a direct pass-through of an already-categorical Foundation fact, an
exact-zero-boundary sign classification of a deterministic arithmetic
difference, or an exact-count presence/agreement tri-state.

One pooled ``ExternalIntelligenceDimension`` covers every Stage 4F analyst's
vocabulary (mirrors ``AnalysisDimension`` covering all six Flow analysts),
differentiated by ``analyst_type`` + ``dimension``, not by separate
per-analyst enum files. Several state enums below are shared across more
than one dimension where the underlying comparison shape is identical
(e.g. ``TrendDirection`` backs ``ACTIVITY_TREND``, ``SUPPLY_TREND``,
``STABLECOIN_SUPPLY_TREND`` and ``EXCHANGE_BALANCE_TREND`` alike) - mirrors
``OrdinalTrend`` being reused across Flow's own window-trend comparisons
rather than one enum per feature.
"""

from __future__ import annotations

from enum import StrEnum


class ExternalIntelligenceAnalystType(StrEnum):
    """Identifies which Stage 4F specialist produced an ``ExternalIntelligenceAnalysisResult``."""

    MACRO_EVENT = "MACRO_EVENT"
    RATES_YIELD = "RATES_YIELD"
    NEWS_SENTIMENT = "NEWS_SENTIMENT"
    ON_CHAIN = "ON_CHAIN"


class ExternalIntelligenceOutcome(StrEnum):
    """Whether an analyst produced observations or abstained outright."""

    ANALYZED = "ANALYZED"
    ABSTAINED = "ABSTAINED"


class ExternalIntelligenceDimension(StrEnum):
    """What aspect of external intelligence one observation describes."""

    # Macro Event Analyst
    EVENT_IMPORTANCE = "EVENT_IMPORTANCE"
    EVENT_PROXIMITY = "EVENT_PROXIMITY"
    EVENT_PRESENCE = "EVENT_PRESENCE"
    SURPRISE = "SURPRISE"
    ACTUAL_VS_PREVIOUS = "ACTUAL_VS_PREVIOUS"
    REVISION_DIRECTION = "REVISION_DIRECTION"

    # Rates / Yield Analyst
    POLICY_RATE_TREND = "POLICY_RATE_TREND"
    YIELD_TREND = "YIELD_TREND"
    CURVE_SLOPE = "CURVE_SLOPE"
    CURVE_SLOPE_TREND = "CURVE_SLOPE_TREND"
    REAL_NOMINAL_RELATIONSHIP = "REAL_NOMINAL_RELATIONSHIP"

    # News / Sentiment Analyst
    RELEVANT_ITEM_PRESENCE = "RELEVANT_ITEM_PRESENCE"
    PER_PROVIDER_SENTIMENT_SIGN = "PER_PROVIDER_SENTIMENT_SIGN"
    SENTIMENT_PROVIDER_AGREEMENT = "SENTIMENT_PROVIDER_AGREEMENT"

    # On-Chain Analyst
    ACTIVITY_TREND = "ACTIVITY_TREND"
    SUPPLY_TREND = "SUPPLY_TREND"
    STABLECOIN_SUPPLY_TREND = "STABLECOIN_SUPPLY_TREND"
    EXCHANGE_NET_FLOW = "EXCHANGE_NET_FLOW"
    EXCHANGE_BALANCE_TREND = "EXCHANGE_BALANCE_TREND"
    STABLECOIN_NET_ISSUANCE = "STABLECOIN_NET_ISSUANCE"


class EventProximityState(StrEnum):
    """Deterministic relationship between one event's ``event_time`` and ``analysis_time``.

    ``ALREADY_OCCURRED`` takes priority over the window comparison: an
    event whose ``event_time`` is strictly before ``analysis_time`` is
    always ``ALREADY_OCCURRED``, regardless of ``proximity_window``. A
    future ``event_time`` exactly at ``analysis_time`` counts as not yet
    occurred (``WITHIN_WINDOW``/``OUTSIDE_WINDOW``), never
    ``ALREADY_OCCURRED`` - see ``app.external_intelligence_analysts.macro_event``.
    """

    WITHIN_WINDOW = "WITHIN_WINDOW"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    ALREADY_OCCURRED = "ALREADY_OCCURRED"


class EventPresenceState(StrEnum):
    """Exact-count presence of caller-supplied events for one scope - never a density judgment."""

    MULTIPLE_EVENTS = "MULTIPLE_EVENTS"
    SINGLE_EVENT = "SINGLE_EVENT"
    NO_EVENTS = "NO_EVENTS"


class SurpriseDirection(StrEnum):
    """Sign of ``actual - forecast`` - never mapped to bullish/bearish."""

    ABOVE_FORECAST = "ABOVE_FORECAST"
    BELOW_FORECAST = "BELOW_FORECAST"
    AT_FORECAST = "AT_FORECAST"


class ActualVsPreviousDirection(StrEnum):
    """Sign of ``actual - previous``."""

    ABOVE_PREVIOUS = "ABOVE_PREVIOUS"
    BELOW_PREVIOUS = "BELOW_PREVIOUS"
    AT_PREVIOUS = "AT_PREVIOUS"


class RevisionDirection(StrEnum):
    """Sign of ``latest_revision.actual - prior_revision.actual``."""

    REVISED_UP = "REVISED_UP"
    REVISED_DOWN = "REVISED_DOWN"
    UNCHANGED = "UNCHANGED"


class RateTrend(StrEnum):
    """Sign of a policy-rate or yield value change between two observations of one series."""

    RISING = "RISING"
    FALLING = "FALLING"
    UNCHANGED = "UNCHANGED"


class CurveSlopeState(StrEnum):
    """Sign of ``long_tenor.value - short_tenor.value`` for one compatible tenor pair."""

    NORMAL = "NORMAL"
    INVERTED = "INVERTED"
    FLAT = "FLAT"


class CurveSlopeTrend(StrEnum):
    """Sign of the change in one tenor pair's slope between two observation times.

    ``STEEPENING`` means the long-minus-short spread increased (moved
    toward normal); ``FLATTENING`` means it decreased (moved toward
    inverted) - a purely structural definition of the spread's own change,
    not an economic claim.
    """

    STEEPENING = "STEEPENING"
    FLATTENING = "FLATTENING"
    UNCHANGED = "UNCHANGED"


class RealNominalRelationship(StrEnum):
    """Sign of ``nominal.value - real.value`` for one compatible tenor/time pair."""

    NOMINAL_ABOVE_REAL = "NOMINAL_ABOVE_REAL"
    NOMINAL_BELOW_REAL = "NOMINAL_BELOW_REAL"
    AT_PARITY = "AT_PARITY"


class RelevantItemPresence(StrEnum):
    """Exact presence of at least one relevance-matched news item for the queried symbol."""

    ITEMS_FOUND = "ITEMS_FOUND"
    NO_ITEMS = "NO_ITEMS"


class SentimentSign(StrEnum):
    """Sign tally of one sentiment provider's reported scores among relevant, recent items.

    ``MIXED`` means that one provider's own relevant items disagreed in
    sign - never resolved by averaging.
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ZERO = "ZERO"
    MIXED = "MIXED"


class SentimentAgreementVerdict(StrEnum):
    """Cross-provider tally of each provider's own unambiguous sign - never a numeric blend."""

    ALL_AGREE = "ALL_AGREE"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TrendDirection(StrEnum):
    """Sign of a quantity's change between the two most recent observations of one series.

    Shared across ``ACTIVITY_TREND``, ``SUPPLY_TREND``,
    ``STABLECOIN_SUPPLY_TREND`` and ``EXCHANGE_BALANCE_TREND`` - the same
    structural "did this quantity go up, down, or stay the same" question
    applied to different metrics, mirroring ``OrdinalTrend``'s reuse across
    Flow's own window-trend comparisons.
    """

    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    UNCHANGED = "UNCHANGED"


class ExchangeNetFlowState(StrEnum):
    """Sign of ``inflow - outflow`` within one ``ExchangeFlowObservation`` carrying both."""

    NET_INFLOW = "NET_INFLOW"
    NET_OUTFLOW = "NET_OUTFLOW"
    BALANCED = "BALANCED"


class StablecoinNetIssuanceState(StrEnum):
    """Sign of ``mint_amount - burn_amount`` within one ``StablecoinSupplyObservation`` carrying both."""

    NET_MINT = "NET_MINT"
    NET_BURN = "NET_BURN"
    BALANCED = "BALANCED"


__all__ = [
    "ActualVsPreviousDirection",
    "CurveSlopeState",
    "CurveSlopeTrend",
    "EventPresenceState",
    "EventProximityState",
    "ExchangeNetFlowState",
    "ExternalIntelligenceAnalystType",
    "ExternalIntelligenceDimension",
    "ExternalIntelligenceOutcome",
    "RateTrend",
    "RealNominalRelationship",
    "RelevantItemPresence",
    "RevisionDirection",
    "SentimentAgreementVerdict",
    "SentimentSign",
    "StablecoinNetIssuanceState",
    "SurpriseDirection",
    "TrendDirection",
]
