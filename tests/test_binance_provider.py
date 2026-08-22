"""BinanceMarketDataProvider end-to-end behaviour against a mock transport.

Payload shapes follow the public Binance documentation; all values are
synthetic. No network access happens here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.core.enums import InstrumentStatus, Timeframe
from app.market_data.exceptions import (
    InvalidProviderResponseError,
    ProviderUnavailableError,
    UnknownSymbolError,
    UnsupportedTimeframeError,
)
from app.market_data.protocols import MarketDataProvider
from app.market_data.providers.binance import BinanceMarketDataProvider, BinanceRestClient
from app.market_data.providers.binance.constants import (
    BINANCE_SPOT_BASE_URL,
    BOOK_TICKER_PATH,
    EXCHANGE_INFO_PATH,
    KLINES_PATH,
    TICKER_PRICE_PATH,
)


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _kline_row(open_time: datetime, close_price: str = "104.20") -> list[object]:
    return [
        _millis(open_time),
        "100.10",
        "105.50",
        "99.90",
        close_price,
        "12.34567890",
        _millis(open_time + timedelta(minutes=5)) - 1,
        "1287654.12",
        842,
        "6.1",
        "640000.5",
        "0",
    ]


def _exchange_info(now: datetime) -> dict[str, object]:
    return {
        "timezone": "UTC",
        "serverTime": _millis(now),
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.00001000",
                        "minQty": "0.00001000",
                        "maxQty": "9000.00000000",
                    },
                    {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                ],
            }
        ],
    }


def _provider(
    routes: Mapping[str, object] | Callable[[httpx.Request], httpx.Response],
    now: datetime,
) -> BinanceMarketDataProvider:
    """Build a provider whose HTTP layer is served from ``routes``."""
    if callable(routes):
        handler = routes
    else:

        def handler(request: httpx.Request) -> httpx.Response:
            payload = routes.get(request.url.path)
            if payload is None:
                return httpx.Response(404, json={"code": -1121, "msg": "Invalid symbol."})
            return httpx.Response(200, json=payload)

    client = BinanceRestClient(
        http_client=httpx.Client(
            base_url=BINANCE_SPOT_BASE_URL, transport=httpx.MockTransport(handler)
        )
    )
    return BinanceMarketDataProvider(client, clock=lambda: now)


def test_provider_satisfies_the_protocol(now: datetime) -> None:
    provider = _provider({}, now)
    assert isinstance(provider, MarketDataProvider)


# --------------------------------------------------------------------------- #
# current price
# --------------------------------------------------------------------------- #


def test_get_current_price(now: datetime) -> None:
    provider = _provider(
        {TICKER_PRICE_PATH: {"symbol": "BTCUSDT", "price": "64123.45000000"}}, now
    )
    quote = provider.get_current_price("btcusdt")

    assert quote.symbol == "BTCUSDT"
    assert quote.price == Decimal("64123.45000000")
    assert quote.timestamp == now
    assert quote.timestamp.tzinfo is not None
    assert quote.source == "binance:ticker_price"


def test_get_current_price_rejects_mismatched_symbol(now: datetime) -> None:
    provider = _provider({TICKER_PRICE_PATH: {"symbol": "ETHUSDT", "price": "1"}}, now)
    with pytest.raises(InvalidProviderResponseError, match="does not match requested"):
        provider.get_current_price("BTCUSDT")


def test_get_current_price_rejects_malformed_payload(now: datetime) -> None:
    provider = _provider({TICKER_PRICE_PATH: {"symbol": "BTCUSDT"}}, now)
    with pytest.raises(InvalidProviderResponseError, match="missing field 'price'"):
        provider.get_current_price("BTCUSDT")


def test_unknown_symbol_is_reported(now: datetime) -> None:
    provider = _provider(
        lambda _request: httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."}), now
    )
    with pytest.raises(UnknownSymbolError):
        provider.get_current_price("NOPEUSDT")


def test_network_failure_is_reported(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route to host", request=request)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler, now).get_current_price("BTCUSDT")


# --------------------------------------------------------------------------- #
# bid / ask
# --------------------------------------------------------------------------- #


def test_get_bid_ask(now: datetime) -> None:
    provider = _provider(
        {
            BOOK_TICKER_PATH: {
                "symbol": "BTCUSDT",
                "bidPrice": "64120.10000000",
                "bidQty": "1.50000000",
                "askPrice": "64120.90000000",
                "askQty": "0.75000000",
            }
        },
        now,
    )
    quote = provider.get_bid_ask("BTCUSDT")

    assert quote.bid == Decimal("64120.10000000")
    assert quote.ask == Decimal("64120.90000000")
    assert quote.spread == Decimal("0.80000000")
    assert quote.bid_quantity == Decimal("1.50000000")
    assert quote.timestamp == now
    assert quote.source == "binance:book_ticker"


def test_get_bid_ask_rejects_crossed_quote(now: datetime) -> None:
    provider = _provider(
        {
            BOOK_TICKER_PATH: {
                "symbol": "BTCUSDT",
                "bidPrice": "101",
                "askPrice": "100",
            }
        },
        now,
    )
    with pytest.raises(InvalidProviderResponseError, match="ask 100 is below bid 101"):
        provider.get_bid_ask("BTCUSDT")


def test_get_bid_ask_rejects_negative_quote(now: datetime) -> None:
    provider = _provider(
        {BOOK_TICKER_PATH: {"symbol": "BTCUSDT", "bidPrice": "-5", "askPrice": "1"}}, now
    )
    with pytest.raises(InvalidProviderResponseError, match="negative quote"):
        provider.get_bid_ask("BTCUSDT")


# --------------------------------------------------------------------------- #
# ohlcv
# --------------------------------------------------------------------------- #


def test_get_ohlcv(now: datetime) -> None:
    rows = [_kline_row(now - timedelta(minutes=5)), _kline_row(now, close_price="103.00")]
    provider = _provider({KLINES_PATH: rows}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=2)

    assert len(candles) == 2
    assert candles[0].timestamp == now - timedelta(minutes=5)
    assert candles[-1].close == Decimal("103.00")
    assert all(candle.timestamp.tzinfo is not None for candle in candles)
    assert all(isinstance(candle.volume, Decimal) for candle in candles)


def test_get_ohlcv_sends_mapped_interval(now: datetime) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[_kline_row(now)])

    _provider(handler, now).get_ohlcv("BTCUSDT", Timeframe.H4, limit=1)
    assert seen == {"symbol": "BTCUSDT", "interval": "4h", "limit": "1"}


def test_get_ohlcv_rejects_unsupported_timeframe_without_request(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP request expected")

    with pytest.raises(UnsupportedTimeframeError):
        _provider(handler, now).get_ohlcv("BTCUSDT", Timeframe.M30)


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_get_ohlcv_rejects_out_of_range_limit(now: datetime, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        _provider({}, now).get_ohlcv("BTCUSDT", Timeframe.M5, limit=limit)


def test_get_ohlcv_rejects_empty_result(now: datetime) -> None:
    provider = _provider({KLINES_PATH: []}, now)
    with pytest.raises(InvalidProviderResponseError, match="empty OHLCV result"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_rejects_duplicate_timestamps(now: datetime) -> None:
    provider = _provider({KLINES_PATH: [_kline_row(now), _kline_row(now)]}, now)
    with pytest.raises(InvalidProviderResponseError, match="duplicate candle timestamps"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_rejects_unsorted_candles(now: datetime) -> None:
    rows = [_kline_row(now), _kline_row(now - timedelta(minutes=5))]
    provider = _provider({KLINES_PATH: rows}, now)
    with pytest.raises(InvalidProviderResponseError, match="not ordered by ascending time"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_returns_stale_series_with_warning(
    now: datetime, caplog: pytest.LogCaptureFixture
) -> None:
    rows = [_kline_row(now - timedelta(hours=2)), _kline_row(now - timedelta(hours=1, minutes=55))]
    provider = _provider({KLINES_PATH: rows}, now)

    with caplog.at_level(logging.WARNING):
        candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5)

    assert len(candles) == 2
    assert "stale OHLCV" in caplog.text


def test_get_ohlcv_rejects_malformed_rows(now: datetime) -> None:
    provider = _provider({KLINES_PATH: [[_millis(now), "1", "2"]]}, now)
    with pytest.raises(InvalidProviderResponseError, match="expected at least 6"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


# --------------------------------------------------------------------------- #
# instrument metadata
# --------------------------------------------------------------------------- #


def test_get_instrument_metadata(now: datetime) -> None:
    provider = _provider({EXCHANGE_INFO_PATH: _exchange_info(now)}, now)
    metadata = provider.get_instrument_metadata("btcusdt")

    assert metadata.symbol == "BTCUSDT"
    assert metadata.base_asset == "BTC"
    assert metadata.quote_asset == "USDT"
    assert metadata.status is InstrumentStatus.TRADING
    assert metadata.tick_size == Decimal("0.01")
    assert metadata.price_precision == 2
    assert metadata.step_size == Decimal("0.00001")
    assert metadata.quantity_precision == 5
    assert metadata.min_quantity == Decimal("0.00001")
    assert metadata.max_quantity == Decimal("9000")
    assert metadata.min_notional == Decimal("5")
    assert metadata.source == "binance:exchange_info"
    assert metadata.timestamp == now


def test_get_instrument_metadata_unknown_symbol(now: datetime) -> None:
    payload = _exchange_info(now)
    payload["symbols"] = []
    provider = _provider({EXCHANGE_INFO_PATH: payload}, now)
    with pytest.raises(UnknownSymbolError, match="does not describe symbol"):
        provider.get_instrument_metadata("BTCUSDT")


def test_get_instrument_metadata_rejects_malformed_payload(now: datetime) -> None:
    provider = _provider({EXCHANGE_INFO_PATH: {"serverTime": _millis(now)}}, now)
    with pytest.raises(InvalidProviderResponseError, match="no 'symbols' list"):
        provider.get_instrument_metadata("BTCUSDT")


def test_blank_symbol_is_rejected_before_any_request(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP request expected")

    with pytest.raises(UnknownSymbolError, match="must not be empty"):
        _provider(handler, now).get_current_price("  ")
