"""MT5-backed OHLCV market data provider (Stage A foundation).

Nothing outside this package imports MT5-specifics: callers depend on
``app.market_data.protocols.OHLCVProvider``. No ``MetaTrader5`` import
anywhere in this package - only ``app.mt5.client`` talks to it directly.
"""

from __future__ import annotations

from app.market_data.providers.mt5.mapper import map_mt5_rate, map_mt5_rates
from app.market_data.providers.mt5.provider import H4_RAW_H1_LOOKBACK, MT5_V1_TECHNICAL_TIMEFRAMES, MT5OHLCVProvider
from app.market_data.providers.mt5.resampler import resample_h4
from app.market_data.providers.mt5.timezone import normalize_mt5_server_timestamp

__all__ = [
    "H4_RAW_H1_LOOKBACK",
    "MT5OHLCVProvider",
    "MT5_V1_TECHNICAL_TIMEFRAMES",
    "map_mt5_rate",
    "map_mt5_rates",
    "normalize_mt5_server_timestamp",
    "resample_h4",
]
