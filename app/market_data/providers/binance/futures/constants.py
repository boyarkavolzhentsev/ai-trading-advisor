"""Binance USD-M perpetual futures public REST facts.

Endpoint paths and vocabulary specific to the futures venue family. Kept
separate from ``app.market_data.providers.binance.constants`` (Spot) so Spot
and Futures responsibilities never blend.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.core.enums.market import Timeframe

PROVIDER_NAME: Final[str] = "binance_futures"
"""Distinct from Spot's ``"binance"`` label so provenance can never conflate
a Spot value with a perpetual futures value for the same base symbol."""

BINANCE_FUTURES_BASE_URL: Final[str] = "https://fapi.binance.com"
"""Default public USD-M Futures REST base URL. Overridable per client instance."""

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0

PREMIUM_INDEX_PATH: Final[str] = "/fapi/v1/premiumIndex"
FUNDING_INFO_PATH: Final[str] = "/fapi/v1/fundingInfo"
OPEN_INTEREST_PATH: Final[str] = "/fapi/v1/openInterest"
KLINES_PATH: Final[str] = "/fapi/v1/klines"
DEPTH_PATH: Final[str] = "/fapi/v1/depth"

MAX_KLINES_LIMIT: Final[int] = 1500
"""Largest ``limit`` the public futures klines endpoint accepts."""

DEPTH_LIMITS: Final[frozenset[int]] = frozenset({5, 10, 20, 50, 100, 500, 1000})
"""The only ``limit`` values the public futures order book endpoint accepts."""

DEFAULT_DEPTH_LIMIT: Final[int] = 100

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

TAKER_FLOW_MIN_FIELDS: Final[int] = 11
"""Klines fields needed through ``takerBuyQuoteAssetVolume`` (index 10)."""
