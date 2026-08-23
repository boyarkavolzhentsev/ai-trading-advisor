"""Binance USD-M perpetual futures real-time WebSocket facts.

Endpoint paths and stream-name vocabulary specific to the futures WebSocket
venue. As of the current official documentation, Binance splits USD-M
futures WebSocket market data across two dedicated base paths rather than
one unified endpoint - the legacy unified URL's migration deadline
(2026-04-23) has already passed, so the split endpoints below are required,
not optional:

- ``/public``  - book depth and book-ticker streams
- ``/market``  - aggregate trades, mark price, klines, liquidations

Both are reached under the same host, ``wss://fstream.binance.com``. A
connection to one path does not receive streams that belong to the other.
"""

from __future__ import annotations

from typing import Final

PROVIDER_NAME: Final[str] = "binance_futures"

BINANCE_FUTURES_WS_HOST: Final[str] = "wss://fstream.binance.com"
PUBLIC_WS_BASE_URL: Final[str] = f"{BINANCE_FUTURES_WS_HOST}/public/stream"
"""Book depth and book-ticker streams live here."""

MARKET_WS_BASE_URL: Final[str] = f"{BINANCE_FUTURES_WS_HOST}/market/stream"
"""Aggregate trades, mark price and liquidations live here."""

MAX_STREAMS_PER_CONNECTION: Final[int] = 1024
MAX_INCOMING_CONTROL_MESSAGES_PER_SECOND: Final[int] = 10
CONNECTION_LIFETIME_HOURS: Final[int] = 24
"""Binance forcibly closes a connection after this long; the transport's
reconnect loop re-establishes it and replays subscriptions."""

DEPTH_UPDATE_SPEED: Final[str] = "100ms"
DEFAULT_MARK_PRICE_UPDATE_SPEED: Final[str] = "1s"

ALL_MARKET_LIQUIDATION_STREAM: Final[str] = "!forceOrder@arr"
"""All-symbol liquidation stream. Per Binance's own documentation this is
still throttled to the single largest liquidation order per symbol within
each 1000ms window - it is a wider feed (every symbol) than the per-symbol
stream, not an unthrottled one."""


def depth_stream_name(symbol: str, *, update_speed: str = DEPTH_UPDATE_SPEED) -> str:
    return f"{symbol.lower()}@depth@{update_speed}"


def agg_trade_stream_name(symbol: str) -> str:
    return f"{symbol.lower()}@aggTrade"


def mark_price_stream_name(symbol: str, *, update_speed: str = DEFAULT_MARK_PRICE_UPDATE_SPEED) -> str:
    suffix = f"@{update_speed}" if update_speed else ""
    return f"{symbol.lower()}@markPrice{suffix}"


def liquidation_stream_name(symbol: str) -> str:
    return f"{symbol.lower()}@forceOrder"


__all__ = [
    "ALL_MARKET_LIQUIDATION_STREAM",
    "BINANCE_FUTURES_WS_HOST",
    "CONNECTION_LIFETIME_HOURS",
    "DEFAULT_MARK_PRICE_UPDATE_SPEED",
    "DEPTH_UPDATE_SPEED",
    "MARKET_WS_BASE_URL",
    "MAX_INCOMING_CONTROL_MESSAGES_PER_SECOND",
    "MAX_STREAMS_PER_CONNECTION",
    "PROVIDER_NAME",
    "PUBLIC_WS_BASE_URL",
    "agg_trade_stream_name",
    "depth_stream_name",
    "liquidation_stream_name",
    "mark_price_stream_name",
]
