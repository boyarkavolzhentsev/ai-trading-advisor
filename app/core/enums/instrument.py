"""Instrument trading status and contract identity enums."""

from __future__ import annotations

from enum import StrEnum


class InstrumentStatus(StrEnum):
    """Provider-agnostic trading status of an instrument.

    Every data provider uses its own vocabulary; adapters map it onto these
    values so core code never branches on provider-specific strings.
    """

    TRADING = "TRADING"
    HALTED = "HALTED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ContractType(StrEnum):
    """Kind of tradable contract behind a symbol.

    The same base symbol (e.g. ``BTCUSDT``) can denote unrelated instruments
    across markets - a Spot pair and a perpetual futures contract settle,
    fund and margin differently. Every contract-bearing model carries this so
    the two can never be silently treated as the same instrument.
    """

    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"
