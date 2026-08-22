"""Market regime enum."""

from __future__ import annotations

from enum import StrEnum


class MarketRegime(StrEnum):
    """Classified market regime.

    Values are not mutually exclusive in reality (a market can be trending and
    highly volatile), so consumers may carry a collection of regimes rather
    than a single value.
    """

    TRENDING = "TRENDING"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    UNKNOWN = "UNKNOWN"
