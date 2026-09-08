"""High-Impact Event Risk Gate vocabulary (Corrective V1 Integration).

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, a confidence score, or a probability. Every value describes
either a per-family temporal-safety verdict, the exact structural reason one
family was blocked, an event's provider-reported importance tier, or the
freshness of the upstream MQL5 calendar bridge - never a directional
interpretation of any event's content. This gate never decides direction;
that remains Judge's exclusive authority, untouched here.
"""

from __future__ import annotations

from enum import StrEnum


class HighImpactEventVerdict(StrEnum):
    """Per-family temporal-safety verdict for issuing a NEW recommendation.

    Never a trade approval and never evidence of direction: ``ALLOWED``/
    ``WARNED`` mean only that the family's ``CandidateTradeSetup`` validity
    window does not (``ALLOWED``) or does but non-blockingly (``WARNED``)
    coincide with a tracked high-impact event's window. ``WARNED`` is
    deliberately non-blocking in V1 - see the approved design report.
    """

    ALLOWED = "ALLOWED"
    WARNED = "WARNED"
    BLOCKED = "BLOCKED"


class HighImpactEventBlockReason(StrEnum):
    """Exact structural reason one family was blocked.

    Single V1 member: every block is the same structural fact - the
    family's ``[signal_time, valid_until]`` interval overlaps a relevant
    tracked event's BLOCK window. No release-value/surprise-based reason
    exists in V1 (see the approved design report, "No release-value
    ingestion in V1").
    """

    EVENT_WINDOW_OVERLAP = "EVENT_WINDOW_OVERLAP"


class HighImpactEventImportance(StrEnum):
    """Provider-reported importance tier, passed through unchanged.

    Mirrors the four-member MQL5 ``ENUM_CALENDAR_EVENT_IMPORTANCE``
    vocabulary (``NONE``/``LOW``/``MODERATE``/``HIGH``) rather than reusing
    ``app.core.enums.economic_calendar.EconomicEventImportance`` (a
    three-member, ``app.macro``-owned enum this gate must not depend on -
    see the approved design report's module-boundary requirements). Never
    inferred or upgraded by this gate: only ``HIGH`` is eligible for a hard
    BLOCK, and only when the event is also on the V1 hard-block allowlist.
    """

    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class HighImpactEventDataQuality(StrEnum):
    """Freshness/usability of the upstream MQL5 calendar bridge file.

    Always present on every ``HighImpactEventFamilyResult`` - never
    swallowed. ``STALE``/``UNAVAILABLE``/``MALFORMED`` never block issuance
    by themselves (fail-open, per the approved design report): Portfolio V1
    must remain usable without the bridge.
    """

    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


__all__ = [
    "HighImpactEventBlockReason",
    "HighImpactEventDataQuality",
    "HighImpactEventImportance",
    "HighImpactEventVerdict",
]
