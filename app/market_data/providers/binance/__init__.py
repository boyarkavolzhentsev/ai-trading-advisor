"""Binance Spot public REST market data provider.

Nothing outside this package imports Binance specifics: callers depend on
``app.market_data.protocols.MarketDataProvider``.
"""

from __future__ import annotations

from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.constants import (
    BINANCE_SPOT_BASE_URL,
    PROVIDER_NAME,
    SUPPORTED_SYMBOLS,
    TIMEFRAME_INTERVALS,
)
from app.market_data.providers.binance.provider import BinanceMarketDataProvider

__all__ = [
    "BINANCE_SPOT_BASE_URL",
    "PROVIDER_NAME",
    "SUPPORTED_SYMBOLS",
    "TIMEFRAME_INTERVALS",
    "BinanceMarketDataProvider",
    "BinanceRestClient",
]
