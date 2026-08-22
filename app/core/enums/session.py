"""Trading session / cycle status enum."""

from __future__ import annotations

from enum import StrEnum


class TradingSessionStatus(StrEnum):
    """Operational state of a trading session within a trading cycle.

    Transitions are driven by the future target/session manager from equity,
    daily risk usage and cycle drawdown; no logic is implemented yet.
    """

    ACTIVE = "ACTIVE"
    REDUCED_RISK = "REDUCED_RISK"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    TARGET_REACHED = "TARGET_REACHED"
    LOSS_LIMIT_REACHED = "LOSS_LIMIT_REACHED"
    LOCKED = "LOCKED"
