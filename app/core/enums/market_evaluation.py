"""Stage 5A market-evaluation enums - deterministic vocabulary only.

No member here ever means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a
qualitative market judgment, or a magnitude-threshold-derived label. Every
enum below describes either contour participation (evidence-availability,
mirroring ``FlowSupervisorOutcome``/``TechnicalSupervisorOutcome``/
``ExternalIntelligenceSupervisorOutcome`` one layer up) or the structural
basis on which one External Intelligence scope was found relevant to a
``MarketEvaluationContext`` - never a comparison of what any contour's
evidence *says*.
"""

from __future__ import annotations

from enum import StrEnum


class MarketEvaluationContourStatus(StrEnum):
    """Per-contour evidence-availability verdict, normalized across Flow/
    Technical/External Intelligence's identically-shaped native outcomes,
    plus ``MISSING`` for a contour that was not supplied at all - a state
    none of the three native enums has, since each of them always reflects
    at least one attempted call."""

    MISSING = "MISSING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PARTIAL = "PARTIAL"
    ANALYZED = "ANALYZED"


class MarketEvaluationOutcome(StrEnum):
    """Top-level, participation-derived verdict across all three contours.

    Describes contour participation only - never trade eligibility, market
    quality, signal strength, confidence, direction, or recommendation.
    """

    EVALUATED = "EVALUATED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ExternalScopeMatchKind(StrEnum):
    """Which explicit ``MarketEvaluationContext`` field a matched Stage 4G
    scope was aligned on. Bookkeeping only: never implies agreement,
    direction, or any interpretation of the scope's own evidence."""

    SYMBOL = "SYMBOL"
    ASSET_NETWORK = "ASSET_NETWORK"
    CURRENCY = "CURRENCY"


class ExternalAlignmentStatus(StrEnum):
    """Whether the supplied External Intelligence result had any scope
    relevant to this evaluation's context - independent of
    ``external_status`` (Stage 4G may have analyzed evidence for scopes
    unrelated to this context; that is a valid, expected combination, not a
    contradiction)."""

    MISSING = "MISSING"
    NO_MATCHING_SCOPE = "NO_MATCHING_SCOPE"
    MATCHED = "MATCHED"


__all__ = [
    "ExternalAlignmentStatus",
    "ExternalScopeMatchKind",
    "MarketEvaluationContourStatus",
    "MarketEvaluationOutcome",
]
