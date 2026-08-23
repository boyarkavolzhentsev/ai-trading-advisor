"""BinanceRestLiquidationProvider: REST placeholder behaviour.

Binance exposes forced liquidations only through the ``forceOrder`` WebSocket
stream. This adapter must satisfy ``LiquidationProvider`` today without ever
touching the network - every call raises ``DataNotAvailableError``
immediately.
"""

from __future__ import annotations

import pytest

from app.market_data.exceptions import DataNotAvailableError
from app.market_data.protocols import LiquidationProvider
from app.market_data.providers.binance.futures import BinanceRestLiquidationProvider


def test_liquidation_provider_satisfies_the_protocol() -> None:
    assert isinstance(BinanceRestLiquidationProvider(), LiquidationProvider)


def test_get_recent_liquidations_raises_without_any_request() -> None:
    provider = BinanceRestLiquidationProvider()
    with pytest.raises(DataNotAvailableError, match="WebSocket"):
        provider.get_recent_liquidations("BTCUSDT")


def test_get_recent_liquidations_raises_regardless_of_limit() -> None:
    provider = BinanceRestLiquidationProvider()
    with pytest.raises(DataNotAvailableError):
        provider.get_recent_liquidations("BTCUSDT", limit=1000)


def test_get_recent_liquidations_raises_for_any_symbol_spelling() -> None:
    provider = BinanceRestLiquidationProvider()
    with pytest.raises(DataNotAvailableError):
        provider.get_recent_liquidations("  not-a-real-symbol  ")


def test_get_recent_liquidations_issues_no_http_client() -> None:
    """The provider carries no HTTP client at all - construction alone proves
    a request can never be issued, in addition to the raise itself."""
    provider = BinanceRestLiquidationProvider()
    assert not hasattr(provider, "_client")
