"""Stage 10C symbol/broker trading-constraint vocabulary."""

from __future__ import annotations

from enum import StrEnum


class MT5SymbolTradeMode(StrEnum):
    """Normalized broker trade-mode restriction for one symbol, mapped from
    the raw MT5 ``SYMBOL_TRADE_MODE_*`` integer constant by
    ``app.mt5.client`` - never exposed as a raw integer outside that module.

    The real MT5 API reports exactly five raw values:
    ``SYMBOL_TRADE_MODE_DISABLED``, ``_LONGONLY``, ``_SHORTONLY``,
    ``_CLOSEONLY`` and ``_FULL``. Any unrecognized future raw value maps to
    ``UNKNOWN`` rather than raising - and ``UNKNOWN`` is treated as
    non-tradable by ``app.mt5.sizing`` (fail closed), mirroring
    ``AccountPositionMode``'s own raw-integer-mapping precedent while
    differing in what ``UNKNOWN`` implies downstream: margin mode's
    ``UNKNOWN`` gates nothing, but a symbol whose trade restriction cannot be
    recognized can never be safely claimed tradable.
    """

    DISABLED = "DISABLED"
    LONG_ONLY = "LONG_ONLY"
    SHORT_ONLY = "SHORT_ONLY"
    CLOSE_ONLY = "CLOSE_ONLY"
    FULL = "FULL"
    UNKNOWN = "UNKNOWN"


__all__ = ["MT5SymbolTradeMode"]
