"""Market domain and timeframe enums."""

from __future__ import annotations

from enum import StrEnum


class MarketType(StrEnum):
    """Market domain a symbol belongs to.

    Each value maps to a future market domain supervisor under ``app/markets``.
    """

    US = "US"
    EU = "EU"
    FX = "FX"
    CRYPTO = "CRYPTO"
    METALS = "METALS"
    ENERGIES = "ENERGIES"


class Timeframe(StrEnum):
    """Candle / analysis timeframe."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
