"""``OHLCVProvider`` protocol conformance. The MT5 provider must satisfy the
narrow ``OHLCVProvider`` contract and must NOT structurally fake
``FuturesMarketDataProvider``'s unrelated funding/open-interest/taker-flow/
order-book capabilities, which it does not have."""

from __future__ import annotations

from app.market_data.protocols import FuturesMarketDataProvider, MarketDataProvider, OHLCVProvider
from app.market_data.providers.mt5.provider import MT5OHLCVProvider


def _mt5_provider() -> MT5OHLCVProvider:
    # Construction performs no I/O and calls no client method, so any
    # placeholder satisfies the (unused, for this test) ``client`` dependency.
    return MT5OHLCVProvider(client=object(), server_timezone="UTC")  # type: ignore[arg-type]


def test_mt5_provider_satisfies_ohlcv_provider() -> None:
    assert isinstance(_mt5_provider(), OHLCVProvider)


def test_mt5_provider_does_not_satisfy_futures_market_data_provider() -> None:
    """The MT5 provider must not fake funding/open-interest/taker-flow/
    order-book capabilities it does not have."""
    assert isinstance(_mt5_provider(), FuturesMarketDataProvider) is False


def test_mt5_provider_does_not_satisfy_market_data_provider() -> None:
    """Nor current-price/bid-ask/instrument-metadata capabilities."""
    assert isinstance(_mt5_provider(), MarketDataProvider) is False
