"""Stage 4A economic-calendar enums - normalized facts only, no interpretation.

No member here encodes a computed surprise, an inferred importance, or a
qualitative policy-stance judgment - see ``app.core.models.economic_event``
for the facts-only contract this vocabulary backs. ``EconomicCategory`` is
deliberately compact: it covers the Stage 4A scope only, with ``OTHER`` as the
explicit escape hatch for a genuinely unmapped provider category (paired with
``EconomicEvent.category_raw`` so no provider label is ever silently
discarded).
"""

from __future__ import annotations

from enum import StrEnum


class EconomicCategory(StrEnum):
    """Normalized macro release category, independent of any one provider's naming."""

    CPI = "CPI"
    CORE_CPI = "CORE_CPI"
    PPI = "PPI"
    PCE = "PCE"
    CORE_PCE = "CORE_PCE"
    NON_FARM_PAYROLLS = "NON_FARM_PAYROLLS"
    UNEMPLOYMENT_RATE = "UNEMPLOYMENT_RATE"
    JOBLESS_CLAIMS = "JOBLESS_CLAIMS"
    GDP = "GDP"
    RETAIL_SALES = "RETAIL_SALES"
    PMI_ISM = "PMI_ISM"
    CONSUMER_CONFIDENCE = "CONSUMER_CONFIDENCE"
    RATE_DECISION = "RATE_DECISION"
    OTHER = "OTHER"


class EconomicEventStatus(StrEnum):
    """Lifecycle state of one economic-calendar record.

    Distinct from data quality (``app.core.models.data_quality.DataQuality``):
    a ``SCHEDULED`` event with ``actual=None`` is a legitimate, valid state,
    never ``UNAVAILABLE`` - that vocabulary belongs one layer up and is never
    merged with lifecycle here. ``STALE`` is deliberately absent from this
    enum: "too old to matter" is a consumer/query-horizon judgment, not a fact
    about the event itself. ``POSTPONED``/``CANCELLED`` must never be inferred
    from a late ``event_time`` - only ever set from an explicit provider
    signal (see ``app.macro.quality.infer_status``).
    """

    SCHEDULED = "SCHEDULED"
    RELEASED = "RELEASED"
    REVISED = "REVISED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"


class EconomicEventImportance(StrEnum):
    """Provider-reported importance tier, passed through unchanged.

    Never inferred or hardcoded by this system (e.g. "CPI is always HIGH"):
    populated only when a provider explicitly supplies a tier for a specific
    release. Absent that, ``EconomicEvent.importance`` stays ``None`` - there
    is no default and no internal numeric impact score.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CentralBank(StrEnum):
    """Central bank identity for a ``RateDecisionDetail``."""

    FED = "FED"
    ECB = "ECB"
    BOE = "BOE"
    BOJ = "BOJ"
    OTHER = "OTHER"


__all__ = [
    "CentralBank",
    "EconomicCategory",
    "EconomicEventImportance",
    "EconomicEventStatus",
]
