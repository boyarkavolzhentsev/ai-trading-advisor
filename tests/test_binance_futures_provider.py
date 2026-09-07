"""BinanceFuturesMarketDataProvider end-to-end behaviour against a mock transport.

Payload shapes follow the public Binance USD-M futures documentation; all
values are synthetic. No network access happens here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.exceptions import (
    InvalidProviderResponseError,
    ProviderUnavailableError,
    UnknownSymbolError,
    UnsupportedTimeframeError,
)
from app.market_data.protocols import FuturesMarketDataProvider
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures import BinanceFuturesMarketDataProvider
from app.market_data.providers.binance.futures.constants import (
    BINANCE_FUTURES_BASE_URL,
    DEPTH_PATH,
    FUNDING_INFO_PATH,
    KLINES_PATH,
    OPEN_INTEREST_PATH,
    PREMIUM_INDEX_PATH,
)


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _futures_kline_row(open_time: datetime, taker_buy: str = "7.5") -> list[object]:
    return [
        _millis(open_time),
        "100.10",
        "105.50",
        "99.90",
        "104.20",
        "12.5",
        _millis(open_time + timedelta(minutes=5)) - 1,
        "1300000.00",
        800,
        taker_buy,
        "780000.00",
        "0",
    ]


def _provider(
    routes: Mapping[str, object] | Callable[[httpx.Request], httpx.Response],
    now: datetime,
) -> BinanceFuturesMarketDataProvider:
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
            base_url=BINANCE_FUTURES_BASE_URL, transport=httpx.MockTransport(handler)
        )
    )
    return BinanceFuturesMarketDataProvider(client, clock=lambda: now)


def test_provider_satisfies_the_protocol(now: datetime) -> None:
    provider = _provider({}, now)
    assert isinstance(provider, FuturesMarketDataProvider)


# --------------------------------------------------------------------------- #
# funding rate
# --------------------------------------------------------------------------- #


def test_get_funding_rate(now: datetime) -> None:
    provider = _provider(
        {
            PREMIUM_INDEX_PATH: {
                "symbol": "BTCUSDT",
                "markPrice": "64100.50",
                "indexPrice": "64099.10",
                "lastFundingRate": "0.00010000",
                "nextFundingTime": _millis(now + timedelta(hours=4)),
                "time": _millis(now),
            },
            FUNDING_INFO_PATH: [{"symbol": "BTCUSDT", "fundingIntervalHours": 4}],
        },
        now,
    )
    funding = provider.get_funding_rate("btcusdt")

    assert funding.symbol == "BTCUSDT"
    assert funding.contract_type is ContractType.PERPETUAL
    assert funding.funding_rate == Decimal("0.00010000")
    assert funding.funding_interval_hours == 4
    assert funding.source == "binance_futures:funding_rate"


def test_get_funding_rate_interval_is_none_when_not_disclosed(now: datetime) -> None:
    provider = _provider(
        {
            PREMIUM_INDEX_PATH: {
                "symbol": "BTCUSDT",
                "markPrice": "1",
                "indexPrice": "1",
                "lastFundingRate": "0",
                "nextFundingTime": 0,
                "time": _millis(now),
            },
            FUNDING_INFO_PATH: [],
        },
        now,
    )
    funding = provider.get_funding_rate("BTCUSDT")
    assert funding.funding_interval_hours is None


def test_get_funding_rate_rejects_mismatched_symbol(now: datetime) -> None:
    provider = _provider(
        {
            PREMIUM_INDEX_PATH: {
                "symbol": "ETHUSDT",
                "markPrice": "1",
                "indexPrice": "1",
                "lastFundingRate": "0",
                "time": _millis(now),
            },
            FUNDING_INFO_PATH: [],
        },
        now,
    )
    with pytest.raises(InvalidProviderResponseError, match="does not match requested"):
        provider.get_funding_rate("BTCUSDT")


def test_get_funding_rate_network_failure_is_reported(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route", request=request)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler, now).get_funding_rate("BTCUSDT")


def test_unknown_symbol_is_reported(now: datetime) -> None:
    provider = _provider(
        lambda _request: httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."}), now
    )
    with pytest.raises(UnknownSymbolError):
        provider.get_funding_rate("NOPEUSDT")


# --------------------------------------------------------------------------- #
# open interest
# --------------------------------------------------------------------------- #


def test_get_open_interest(now: datetime) -> None:
    provider = _provider(
        {OPEN_INTEREST_PATH: {"symbol": "BTCUSDT", "openInterest": "12345.6", "time": _millis(now)}},
        now,
    )
    open_interest = provider.get_open_interest("btcusdt")

    assert open_interest.symbol == "BTCUSDT"
    assert open_interest.contract_type is ContractType.PERPETUAL
    assert open_interest.open_interest == Decimal("12345.6")
    assert open_interest.source == "binance_futures:open_interest"


def test_get_open_interest_rejects_mismatched_symbol(now: datetime) -> None:
    provider = _provider(
        {OPEN_INTEREST_PATH: {"symbol": "ETHUSDT", "openInterest": "1", "time": _millis(now)}}, now
    )
    with pytest.raises(InvalidProviderResponseError, match="does not match requested"):
        provider.get_open_interest("BTCUSDT")


# --------------------------------------------------------------------------- #
# taker flow
# --------------------------------------------------------------------------- #


def test_get_taker_flow(now: datetime) -> None:
    rows = [_futures_kline_row(now - timedelta(minutes=5)), _futures_kline_row(now)]
    provider = _provider({KLINES_PATH: rows}, now)
    snapshots = provider.get_taker_flow("BTCUSDT", Timeframe.M5, limit=2)

    assert len(snapshots) == 2
    assert snapshots[0].timestamp == now - timedelta(minutes=5)
    assert snapshots[0].contract_type is ContractType.PERPETUAL
    assert snapshots[0].source == "binance_futures:taker_flow"
    assert all(isinstance(snap.buy_volume, Decimal) for snap in snapshots)


def test_get_taker_flow_sends_mapped_interval(now: datetime) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[_futures_kline_row(now)])

    _provider(handler, now).get_taker_flow("BTCUSDT", Timeframe.H4, limit=1)
    assert seen == {"symbol": "BTCUSDT", "interval": "4h", "limit": "1"}


def test_get_taker_flow_rejects_unsupported_timeframe_without_request(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP request expected")

    with pytest.raises(UnsupportedTimeframeError):
        _provider(handler, now).get_taker_flow("BTCUSDT", Timeframe.M30)


@pytest.mark.parametrize("limit", [0, -1, 1501])
def test_get_taker_flow_rejects_out_of_range_limit(now: datetime, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        _provider({}, now).get_taker_flow("BTCUSDT", Timeframe.M5, limit=limit)


def test_get_taker_flow_rejects_empty_result(now: datetime) -> None:
    provider = _provider({KLINES_PATH: []}, now)
    with pytest.raises(InvalidProviderResponseError, match="empty taker flow result"):
        provider.get_taker_flow("BTCUSDT", Timeframe.M5)


def test_get_taker_flow_sell_volume_normalization(now: datetime) -> None:
    row = _futures_kline_row(now, taker_buy="7.5")
    row[5] = "12.5"
    provider = _provider({KLINES_PATH: [row]}, now)
    snapshot = provider.get_taker_flow("BTCUSDT", Timeframe.M5, limit=1)[0]
    assert snapshot.buy_volume == Decimal("7.5")
    assert snapshot.sell_volume == Decimal("5.0")
    assert snapshot.total_volume == Decimal("12.5")


# --------------------------------------------------------------------------- #
# ohlcv
# --------------------------------------------------------------------------- #


def test_get_ohlcv_requests_correct_endpoint_symbol_interval_and_limit(now: datetime) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[_futures_kline_row(now)])

    _provider(handler, now).get_ohlcv("btcusdt", Timeframe.M5, limit=1)

    assert seen["path"] == KLINES_PATH
    assert seen["symbol"] == "BTCUSDT"
    assert seen["interval"] == "5m"
    assert seen["limit"] == "1"


def test_get_ohlcv_maps_to_existing_ohlcv_candle(now: datetime) -> None:
    provider = _provider({KLINES_PATH: [_futures_kline_row(now)]}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=1)

    assert len(candles) == 1
    candle = candles[0]
    assert isinstance(candle, OHLCVCandle)
    assert candle.open == Decimal("100.10")
    assert candle.high == Decimal("105.50")
    assert candle.low == Decimal("99.90")
    assert candle.close == Decimal("104.20")
    assert candle.volume == Decimal("12.5")


def test_get_ohlcv_timestamp_comes_from_open_time_not_close_time(now: datetime) -> None:
    row = _futures_kline_row(now)
    close_time_field = row[6]
    provider = _provider({KLINES_PATH: [row]}, now)
    candle = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=1)[0]

    assert candle.timestamp == now
    assert _millis(candle.timestamp) != close_time_field


def test_get_ohlcv_preserves_oldest_first_multi_row_order(now: datetime) -> None:
    rows = [
        _futures_kline_row(now - timedelta(minutes=10)),
        _futures_kline_row(now - timedelta(minutes=5)),
        _futures_kline_row(now),
    ]
    provider = _provider({KLINES_PATH: rows}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=3)

    assert [c.timestamp for c in candles] == [
        now - timedelta(minutes=10),
        now - timedelta(minutes=5),
        now,
    ]


def test_get_ohlcv_retains_final_forming_row(now: datetime) -> None:
    """The provider must remain ignorant of candle closedness: a final row
    whose close time is still in the future relative to any reference time
    is returned exactly like every other row - never filtered here."""
    forming_open_time = now  # close time (open_time + 5min - 1ms) is after `now`
    provider = _provider({KLINES_PATH: [_futures_kline_row(forming_open_time)]}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=1)

    assert len(candles) == 1
    assert candles[0].timestamp == forming_open_time


def test_get_ohlcv_51_candle_response_returns_exactly_51(now: datetime) -> None:
    rows = [_futures_kline_row(now - timedelta(minutes=5 * i)) for i in range(50, -1, -1)]
    provider = _provider({KLINES_PATH: rows}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=51)

    assert len(candles) == 51


def test_get_ohlcv_rejects_empty_response(now: datetime) -> None:
    provider = _provider({KLINES_PATH: []}, now)
    with pytest.raises(InvalidProviderResponseError, match="empty OHLCV result"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_rejects_non_list_payload(now: datetime) -> None:
    provider = _provider({KLINES_PATH: {"not": "a list"}}, now)
    with pytest.raises(InvalidProviderResponseError, match="must be a list"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_rejects_short_row(now: datetime) -> None:
    short_row = _futures_kline_row(now)[:5]  # 5 fields, OHLCV_MIN_FIELDS is 6
    provider = _provider({KLINES_PATH: [short_row]}, now)
    with pytest.raises(InvalidProviderResponseError, match="expected at least 6"):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_rejects_non_numeric_ohlc(now: datetime) -> None:
    row = _futures_kline_row(now)
    row[2] = "not-a-number"  # high
    provider = _provider({KLINES_PATH: [row]}, now)
    with pytest.raises(InvalidProviderResponseError):
        provider.get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_sends_unsupported_timeframe_without_request(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP request expected")

    with pytest.raises(UnsupportedTimeframeError):
        _provider(handler, now).get_ohlcv("BTCUSDT", Timeframe.M30)


@pytest.mark.parametrize("limit", [0, -1, 1501])
def test_get_ohlcv_rejects_out_of_range_limit(now: datetime, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between"):
        _provider({}, now).get_ohlcv("BTCUSDT", Timeframe.M5, limit=limit)


@pytest.mark.parametrize("limit", [1, 1500])
def test_get_ohlcv_accepts_boundary_limits(now: datetime, limit: int) -> None:
    rows = [_futures_kline_row(now - timedelta(minutes=5 * i)) for i in range(limit - 1, -1, -1)]
    provider = _provider({KLINES_PATH: rows}, now)
    candles = provider.get_ohlcv("BTCUSDT", Timeframe.M5, limit=limit)
    assert len(candles) == limit


def test_get_ohlcv_network_failure_is_reported(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route", request=request)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler, now).get_ohlcv("BTCUSDT", Timeframe.M5)


def test_get_ohlcv_never_calls_spot_endpoint(now: datetime) -> None:
    from app.market_data.providers.binance.constants import KLINES_PATH as SPOT_KLINES_PATH

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path != SPOT_KLINES_PATH
        return httpx.Response(200, json=[_futures_kline_row(now)])

    _provider(handler, now).get_ohlcv("BTCUSDT", Timeframe.M5)


# --------------------------------------------------------------------------- #
# order book snapshot
# --------------------------------------------------------------------------- #


def test_get_order_book_snapshot(now: datetime) -> None:
    provider = _provider(
        {
            DEPTH_PATH: {
                "lastUpdateId": 42,
                "T": _millis(now),
                "bids": [["64000", "1.5"]],
                "asks": [["64001", "2.0"]],
            }
        },
        now,
    )
    snapshot = provider.get_order_book_snapshot("btcusdt")

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.contract_type is ContractType.PERPETUAL
    assert snapshot.last_update_id == 42
    assert snapshot.bids[0].price == Decimal("64000")
    assert snapshot.source == "binance_futures:order_book"


def test_get_order_book_snapshot_sends_requested_limit(now: datetime) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"lastUpdateId": 1, "bids": [], "asks": []})

    _provider(handler, now).get_order_book_snapshot("BTCUSDT", limit=50)
    assert seen == {"symbol": "BTCUSDT", "limit": "50"}


def test_get_order_book_snapshot_rejects_invalid_limit(now: datetime) -> None:
    with pytest.raises(ValueError, match="limit must be one of"):
        _provider({}, now).get_order_book_snapshot("BTCUSDT", limit=7)


def test_get_order_book_snapshot_rejects_crossed_book(now: datetime) -> None:
    provider = _provider(
        {DEPTH_PATH: {"lastUpdateId": 1, "bids": [["101", "1"]], "asks": [["100", "1"]]}}, now
    )
    with pytest.raises(InvalidProviderResponseError, match="violates OrderBookSnapshot"):
        provider.get_order_book_snapshot("BTCUSDT")


def test_blank_symbol_is_rejected_before_any_request(now: datetime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no HTTP request expected")

    with pytest.raises(UnknownSymbolError, match="must not be empty"):
        _provider(handler, now).get_funding_rate("  ")
