"""Market data fetchers and data validators.

Layering (outside in):

1. provider client — HTTP only, translates transport failures;
2. mapper — normalizes provider payloads into internal contracts;
3. ``DataQualityValidator`` — judges normalized data, emits ``DataQuality``;
4. provider adapter — wires the three together behind
   ``MarketDataProvider``.

Application code depends on ``MarketDataProvider`` and the domain models only,
never on a concrete venue.
"""

from __future__ import annotations

from app.market_data.exceptions import (
    DataNotAvailableError,
    InvalidProviderResponseError,
    MarketDataError,
    ProviderUnavailableError,
    UnknownSymbolError,
    UnsupportedTimeframeError,
)
from app.market_data.protocols import (
    DEFAULT_DEPTH_LIMIT,
    DEFAULT_LIQUIDATION_LIMIT,
    DEFAULT_OHLCV_LIMIT,
    FuturesMarketDataProvider,
    LiquidationProvider,
    MarketDataProvider,
)
from app.market_data.provenance import MarketDataProvenance, MarketDataSource
from app.market_data.timeframes import TIMEFRAME_DURATIONS, timeframe_duration
from app.market_data.validators import DataQualityValidator

__all__ = [
    "DEFAULT_DEPTH_LIMIT",
    "DEFAULT_LIQUIDATION_LIMIT",
    "DEFAULT_OHLCV_LIMIT",
    "TIMEFRAME_DURATIONS",
    "DataNotAvailableError",
    "DataQualityValidator",
    "FuturesMarketDataProvider",
    "InvalidProviderResponseError",
    "LiquidationProvider",
    "MarketDataError",
    "MarketDataProvenance",
    "MarketDataProvider",
    "MarketDataSource",
    "ProviderUnavailableError",
    "UnknownSymbolError",
    "UnsupportedTimeframeError",
    "timeframe_duration",
]
