"""Binance USD-M perpetual futures real-time WebSocket market data.

Kept separate from the REST ``app.market_data.providers.binance.futures``
package: nothing here changes REST behavior, and REST remains the way this
package bootstraps order-book snapshots and funding-interval information.
Callers depend on ``app.market_data.realtime.protocols``, never on this
package directly.
"""

from __future__ import annotations

from app.market_data.providers.binance.futures.realtime.constants import (
    ALL_MARKET_LIQUIDATION_STREAM,
    MARKET_WS_BASE_URL,
    PROVIDER_NAME,
    PUBLIC_WS_BASE_URL,
)
from app.market_data.providers.binance.futures.realtime.funding_cache import (
    FundingIntervalCache,
    make_binance_fetch_all,
)
from app.market_data.providers.binance.futures.realtime.provider import (
    BinanceFuturesMarketStream,
    BinanceFuturesOrderBookStream,
    make_snapshot_fetcher,
)
from app.market_data.providers.binance.futures.realtime.transport import (
    make_market_transport,
    make_public_transport,
)

__all__ = [
    "ALL_MARKET_LIQUIDATION_STREAM",
    "MARKET_WS_BASE_URL",
    "PROVIDER_NAME",
    "PUBLIC_WS_BASE_URL",
    "BinanceFuturesMarketStream",
    "BinanceFuturesOrderBookStream",
    "FundingIntervalCache",
    "make_binance_fetch_all",
    "make_market_transport",
    "make_public_transport",
    "make_snapshot_fetcher",
]
