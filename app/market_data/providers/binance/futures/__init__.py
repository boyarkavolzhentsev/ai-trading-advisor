"""Binance USD-M perpetual futures public REST market data.

Kept separate from ``app.market_data.providers.binance`` (Spot): nothing here
is imported by the Spot package, and nothing in Spot is imported here beyond
the shared, venue-agnostic HTTP transport (``BinanceRestClient``). Callers
depend on ``app.market_data.protocols.FuturesMarketDataProvider`` /
``LiquidationProvider``, never on this package directly.
"""

from __future__ import annotations

from app.market_data.providers.binance.futures.constants import (
    BINANCE_FUTURES_BASE_URL,
    PROVIDER_NAME,
)
from app.market_data.providers.binance.futures.liquidations import BinanceRestLiquidationProvider
from app.market_data.providers.binance.futures.provider import BinanceFuturesMarketDataProvider

__all__ = [
    "BINANCE_FUTURES_BASE_URL",
    "PROVIDER_NAME",
    "BinanceFuturesMarketDataProvider",
    "BinanceRestLiquidationProvider",
]
