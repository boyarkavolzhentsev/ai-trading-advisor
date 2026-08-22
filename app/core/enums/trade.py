"""Trade direction and trade lifecycle enums."""

from __future__ import annotations

from enum import StrEnum


class TradeDirection(StrEnum):
    """Directional bias of an assessment, decision or setup.

    ``NEUTRAL`` means no directional edge, ``WAIT`` means an edge may exist but
    conditions for acting are not met.
    """

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    WAIT = "WAIT"


class TradeStatus(StrEnum):
    """Lifecycle state of a recommended trade.

    ``NOT_FILLED`` / ``EXPIRED`` exist because a signal has a limited execution
    window: a recommendation may never become a position.
    """

    PENDING = "PENDING"
    FILLED = "FILLED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    NOT_FILLED = "NOT_FILLED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
