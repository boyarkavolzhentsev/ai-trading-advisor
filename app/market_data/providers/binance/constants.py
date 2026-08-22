"""Binance Spot public REST facts.

Endpoint paths, interval vocabulary and status vocabulary. Everything here is
provider-specific and must not leak outside this package.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.core.enums.instrument import InstrumentStatus
from app.core.enums.market import Timeframe

PROVIDER_NAME: Final[str] = "binance"

BINANCE_SPOT_BASE_URL: Final[str] = "https://api.binance.com"
"""Default public Spot REST base URL. Overridable per client instance."""

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0

TICKER_PRICE_PATH: Final[str] = "/api/v3/ticker/price"
BOOK_TICKER_PATH: Final[str] = "/api/v3/ticker/bookTicker"
KLINES_PATH: Final[str] = "/api/v3/klines"
EXCHANGE_INFO_PATH: Final[str] = "/api/v3/exchangeInfo"

MAX_KLINES_LIMIT: Final[int] = 1000
"""Largest ``limit`` the public klines endpoint accepts."""

TIMEFRAME_INTERVALS: Final[Mapping[Timeframe, str]] = MappingProxyType(
    {
        Timeframe.M5: "5m",
        Timeframe.M15: "15m",
        Timeframe.H1: "1h",
        Timeframe.H4: "4h",
        Timeframe.D1: "1d",
    }
)
"""Timeframes supported in this stage, mapped to Binance interval strings."""

SUPPORTED_SYMBOLS: Final[frozenset[str]] = frozenset({"BTCUSDT", "ETHUSDT", "XRPUSDT"})
"""Symbols this stage is exercised against.

Advisory only: the client does not reject other symbols, Binance remains the
authority on what exists.
"""

INSTRUMENT_STATUSES: Final[Mapping[str, InstrumentStatus]] = MappingProxyType(
    {
        "TRADING": InstrumentStatus.TRADING,
        "HALT": InstrumentStatus.HALTED,
        "BREAK": InstrumentStatus.HALTED,
        "PRE_TRADING": InstrumentStatus.CLOSED,
        "POST_TRADING": InstrumentStatus.CLOSED,
        "END_OF_DAY": InstrumentStatus.CLOSED,
        "AUCTION_MATCH": InstrumentStatus.HALTED,
    }
)
"""Binance symbol status vocabulary mapped onto the internal enum."""

PRICE_FILTER: Final[str] = "PRICE_FILTER"
LOT_SIZE_FILTER: Final[str] = "LOT_SIZE"
NOTIONAL_FILTER: Final[str] = "NOTIONAL"
MIN_NOTIONAL_FILTER: Final[str] = "MIN_NOTIONAL"

UNKNOWN_SYMBOL_CODES: Final[frozenset[int]] = frozenset({-1121})
"""Binance error codes meaning "invalid symbol"."""

RATE_LIMIT_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 418})
"""Too many requests / IP banned for repeated rate-limit violations."""
