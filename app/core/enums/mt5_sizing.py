"""Stage 10C broker-aware final candidate sizing vocabulary."""

from __future__ import annotations

from enum import StrEnum


class MT5SizingOutcome(StrEnum):
    """Result of one broker-aware final sizing calculation for a single new
    candidate. ``ACTIONABLE`` is the only outcome that carries a populated
    broker volume/actual monetary risk on ``MT5BrokerSizingResult`` - every
    other outcome fails closed with neither field populated."""

    ACTIONABLE = "ACTIONABLE"
    INVALID_CURRENT_PRICE = "INVALID_CURRENT_PRICE"
    SYMBOL_NOT_TRADABLE = "SYMBOL_NOT_TRADABLE"
    INVALID_TICK_ECONOMICS = "INVALID_TICK_ECONOMICS"
    INVALID_VOLUME_CONSTRAINTS = "INVALID_VOLUME_CONSTRAINTS"
    INVALID_STOP_DISTANCE = "INVALID_STOP_DISTANCE"
    BELOW_BROKER_MINIMUM_VOLUME = "BELOW_BROKER_MINIMUM_VOLUME"
    RISK_VERIFICATION_FAILED = "RISK_VERIFICATION_FAILED"


__all__ = ["MT5SizingOutcome"]
