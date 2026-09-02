"""Stage 10B rollover-state vocabulary - deterministic, application-owned
rollover lifecycle facts only.

No member here describes MT5 terminal/account connectivity (that remains
``app.core.enums.mt5_runtime.MT5ConnectivityState``'s exclusive vocabulary -
never duplicated here). Every value describes either how the currently
persisted/established ``MT5RolloverState`` came to exist, or whether a
freshly computed rollover observation is safe to use.
"""

from __future__ import annotations

from enum import StrEnum


class MT5RolloverEstablishmentMode(StrEnum):
    """How the current ``MT5RolloverState.rollover_equity`` was established.

    Exactly three modes are reachable in Stage 10B V1. A fourth, "exact
    boundary instant capture," is deliberately NOT declared: proving that
    an observation happened at the literal broker trading-day boundary
    requires a continuously-running scheduler/heartbeat fact that does not
    exist yet (that is an orchestration-layer concern, out of Stage 10B
    scope). Declaring an unreachable member for it would be a claim this
    stage cannot honor - auditability must not lie about what was actually
    observed, so this enum states only what Stage 10B can actually prove.
    """

    MIDDAY_BOOTSTRAP = "MIDDAY_BOOTSTRAP"
    POST_BOUNDARY_FIRST_OBSERVATION = "POST_BOUNDARY_FIRST_OBSERVATION"
    SAME_DAY_REUSE = "SAME_DAY_REUSE"


class MT5RolloverOutcome(StrEnum):
    """Result of one rollover-state evaluation cycle.

    Deliberately excludes any "account/connectivity unavailable" member:
    that fact is owned exclusively by ``MT5ConnectivityState``. Rollover
    evaluation is only ever attempted once account facts (equity, floating
    PnL) are already known to be available - a caller without them never
    invokes this vocabulary at all, it reports ``MT5ConnectivityState``
    directly instead. ``READY``/``BOOTSTRAPPED_MIDDAY`` are the only two
    outcomes that carry a populated ``MT5RolloverState`` on
    ``MT5RolloverSnapshot`` - every other outcome fails closed.
    """

    READY = "READY"
    BOOTSTRAPPED_MIDDAY = "BOOTSTRAPPED_MIDDAY"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    PERSISTENCE_CORRUPT = "PERSISTENCE_CORRUPT"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"
    FUTURE_STATE = "FUTURE_STATE"


__all__ = [
    "MT5RolloverEstablishmentMode",
    "MT5RolloverOutcome",
]
