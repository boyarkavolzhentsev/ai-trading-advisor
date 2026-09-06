"""Deterministic Runtime Cycle Orchestration vocabulary (Final Runtime
Integration, Part F).

Describes only the coarse outcome of one impure runtime-cycle coordination
attempt, and the outcome of Part F's own NETTING/UNKNOWN account-position-mode
issuance guard - never a trade recommendation, a matching/lifecycle fact (those
remain Stage 10E's exclusive vocabulary), or a ranking/preference across
``StrategyFamily`` results.
"""

from __future__ import annotations

from enum import StrEnum


class RuntimeCycleOutcome(StrEnum):
    """Coarse, orchestration-level classification of one runtime-cycle run.

    ``BLOCKED`` means MT5 connectivity itself was unavailable this cycle -
    nothing downstream (not even existing-tracking advancement, which needs
    at least a confirmed history read) could be attempted.
    ``PARTIAL_DEGRADED`` means the cycle completed without raising, but at
    least one legitimate sub-component could not fully run or persist (e.g.
    positions/history unavailable, Runtime Fact Assembly BLOCKED, a corrupt
    tracked recommendation excluded, a persistence write failure, or a
    NETTING/UNKNOWN issuance guard block) - useful partial work may still be
    present elsewhere on the result. ``READY`` means every attempted
    sub-component succeeded and persisted cleanly.
    """

    READY = "READY"
    PARTIAL_DEGRADED = "PARTIAL_DEGRADED"
    BLOCKED = "BLOCKED"


class NettingIssuanceOutcome(StrEnum):
    """Result of Part F's own NETTING/UNKNOWN account-position-mode issuance
    guard for one target symbol this cycle.

    Never evaluated for ``AccountPositionMode.HEDGING`` (unrestricted by this
    guard - see ``app.orchestration.runtime_cycle``). ``NO_ACTIONABLE_RECOMMENDATIONS``
    is deliberately distinct from ``ALLOWED``: zero actionable
    ``FinalRecommendation``s this cycle is a legitimate business outcome, not
    a safety block, so it must never be reported as either an ``ALLOWED``
    issuance (nothing was issued) or a ``BLOCKED_*`` safety condition (no
    real ambiguity existed). ``BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS``
    never selects a winner among the actionable families - every one of them
    is suppressed together, deterministically, with no ranking/scoring/
    first-family preference of any kind.
    """

    ALLOWED = "ALLOWED"
    NO_ACTIONABLE_RECOMMENDATIONS = "NO_ACTIONABLE_RECOMMENDATIONS"
    BLOCKED_EXISTING_BROKER_POSITION = "BLOCKED_EXISTING_BROKER_POSITION"
    BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION = "BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION"
    BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS = "BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS"


__all__ = ["NettingIssuanceOutcome", "RuntimeCycleOutcome"]
