"""Stage 10E recommendation-to-broker matching vocabulary.

Describes only the outcome space of one matching *attempt* - a purely
technical/procedural fact about whether, and how, a recommendation's
broker-side opening deal was identified this cycle. Deliberately disjoint
from ``app.core.enums.trade.TradeStatus`` (the recommendation's own business
lifecycle): a matching outcome never directly *is* a ``TradeStatus`` value,
and no member here is named to resemble one, so a caller can never conflate
"what this read technically established" with "what the recommendation's
lifecycle is." See ``app.mt5.matching`` for how (and when) a given outcome
is allowed to cause a ``TradeStatus`` transition.
"""

from __future__ import annotations

from enum import StrEnum


class MT5MatchOutcome(StrEnum):
    """Result of one deterministic recommendation <-> broker matching
    attempt.

    Matching operates at the broker *position lifecycle* level
    (``position_id``), not at one individual deal: a broker may split one
    approved order into several entry fills sharing the same ``position_id``,
    so the matching unit is a ``position_id``'s *total* qualifying opening
    volume, never one deal's volume in isolation (see ``app.mt5.matching``).

    Ownership is decided before volume is ever consulted. A ``position_id``
    is a *structurally eligible lifecycle* once its qualifying opening fills
    pass every non-volume hard constraint (symbol, direction, window,
    pre-existing/already-claimed exclusion, first-lifecycle consistency) -
    regardless of whether its total volume happens to equal, undershoot, or
    overshoot ``approved_broker_volume``. V1 has no ranking, scoring, or
    heuristic winner: two or more structurally eligible ``position_id``s -
    in *any* combination of exact/partial/overfilled volume - always means
    unresolved ownership, never a volume-shape-based preference for one over
    the other.

    ``AMBIGUOUS`` fires whenever two or more distinct ``position_id``s are
    structurally eligible lifecycles at once, in any volume-shape
    combination - never resolved by a tie-break, and never limited to only
    the exact-volume ones; ``candidate_position_ids`` carries every such
    ``position_id``. Only once exactly one structurally eligible lifecycle
    remains does its volume classify the result: ``MATCHED`` when its
    qualifying opening fills sum to exactly ``approved_broker_volume``;
    ``PARTIAL_FILL`` when they sum to strictly less - a real fill occurred,
    so this must never be conflated with "no fill" (``NOT_FILLED``); later
    polling within the still-open validity window may observe the remaining
    fill(s) and resolve to ``MATCHED``; ``VOLUME_MISMATCH`` when they sum to
    strictly more - never silently truncated, never accepted as exact
    execution, and never resolved by choosing a subset of fills that happens
    to sum correctly. ``NO_CANDIDATE_YET`` means zero structurally eligible
    lifecycles were found but the recommendation's execution window has not
    yet closed - still awaiting evidence, not a conclusion.
    ``EXPIRED_CONFIRMED_UNFILLED`` means zero structurally eligible
    lifecycles were found, the execution window has closed, AND the history
    read that produced this result genuinely covered the complete window -
    the only outcome that may cause a ``TradeStatus.NOT_FILLED`` transition
    (``AMBIGUOUS``/``PARTIAL_FILL``/``VOLUME_MISMATCH`` never do, however
    much wall-clock time has passed - genuine broker opening evidence
    exists, it is merely inconclusive). ``READ_UNAVAILABLE`` means this
    attempt's broker read did not succeed (or could not be safely
    normalized) - it authorizes no conclusion and no ``TradeStatus``
    transition whatsoever, regardless of how much wall-clock time has
    passed.
    """

    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    PARTIAL_FILL = "PARTIAL_FILL"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"
    NO_CANDIDATE_YET = "NO_CANDIDATE_YET"
    EXPIRED_CONFIRMED_UNFILLED = "EXPIRED_CONFIRMED_UNFILLED"
    READ_UNAVAILABLE = "READ_UNAVAILABLE"


class MT5TrackedRecommendationCreationOutcome(StrEnum):
    """Result of one attempt to create a fresh ``MT5TrackedRecommendation``
    at recommendation-issuance time.

    ``CREATED`` requires the caller-supplied ``pre_existing_position_ids``
    snapshot to have come from a confirmed ``"OK"`` ``positions()`` read -
    never from an ``"UNAVAILABLE"``/``"UNMAPPABLE_POSITION_SIDE"`` one, which
    would silently fabricate "confirmed no pre-existing exposure" from a
    genuinely unknown account state. ``SNAPSHOT_UNAVAILABLE`` is the sole
    fail-closed alternative: no tracked recommendation is created at all
    (never one carrying a guessed/empty snapshot) - the caller must retry
    creation once a confirmed read is available.
    """

    CREATED = "CREATED"
    SNAPSHOT_UNAVAILABLE = "SNAPSHOT_UNAVAILABLE"


__all__ = ["MT5MatchOutcome", "MT5TrackedRecommendationCreationOutcome"]
