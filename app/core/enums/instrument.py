"""Instrument trading status enum."""

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
