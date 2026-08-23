"""Binance-specific WebSocket transport wiring.

Builds the two dedicated connections Binance's USD-M futures API currently
requires (``/public`` for book depth, ``/market`` for trades/mark
price/liquidations) on top of the generic, provider-agnostic
``WebSocketTransport``. No domain parsing happens here - only connection
construction and the Binance SUBSCRIBE/UNSUBSCRIBE control-message shape.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import websockets.exceptions
from websockets.asyncio.client import connect as ws_connect

from app.market_data.providers.binance.futures.realtime.constants import (
    MARKET_WS_BASE_URL,
    PUBLIC_WS_BASE_URL,
)
from app.market_data.realtime.transport import WebSocketTransport

CONNECTION_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    TimeoutError,
    websockets.exceptions.WebSocketException,
)


def build_binance_subscribe_message(method: str, stream_names: Sequence[str], request_id: int) -> str:
    """Binance's SUBSCRIBE/UNSUBSCRIBE control-message shape."""
    return json.dumps({"method": method, "params": list(stream_names), "id": request_id})


def make_public_transport(*, base_url: str = PUBLIC_WS_BASE_URL, **kwargs: object) -> WebSocketTransport:
    """Transport bound to Binance's ``/public`` endpoint (book depth)."""
    return WebSocketTransport(
        connect=lambda: ws_connect(base_url),
        build_subscribe_message=build_binance_subscribe_message,
        connection_errors=CONNECTION_ERRORS,
        **kwargs,
    )


def make_market_transport(*, base_url: str = MARKET_WS_BASE_URL, **kwargs: object) -> WebSocketTransport:
    """Transport bound to Binance's ``/market`` endpoint (trades, mark price, liquidations)."""
    return WebSocketTransport(
        connect=lambda: ws_connect(base_url),
        build_subscribe_message=build_binance_subscribe_message,
        connection_errors=CONNECTION_ERRORS,
        **kwargs,
    )


__all__ = ["build_binance_subscribe_message", "make_market_transport", "make_public_transport"]
