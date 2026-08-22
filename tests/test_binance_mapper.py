"""Binance payload normalization.

All payloads here are hand-written synthetic shapes copied from the public API
documentation, not recorded market data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums import InstrumentStatus, Timeframe
from app.market_data.exceptions import (
    InvalidProviderResponseError,
    UnknownSymbolError,
    UnsupportedTimeframeError,
)
from app.market_data.providers.binance import mapper

SOURCE = "binance:test"


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _kline_row(open_time: datetime) -> list[object]:
    return [
        _millis(open_time),
        "100.10",
        "105.50",
        "99.90",
        "104.20",
        "12.34567890",
        _millis(open_time + timedelta(minutes=5)) - 1,
        "1287654.12",
        842,
        "6.1",
        "640000.5",
        "0",
    ]


def _exchange_info(**symbol_overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
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
    entry.update(symbol_overrides)
    return {"timezone": "UTC", "serverTime": _millis(datetime(2026, 1, 2, 12, 0, tzinfo=UTC)),
            "symbols": [entry]}


# --------------------------------------------------------------------------- #
# timeframe mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("timeframe", "interval"),
    [
        (Timeframe.M5, "5m"),
        (Timeframe.M15, "15m"),
        (Timeframe.H1, "1h"),
        (Timeframe.H4, "4h"),
        (Timeframe.D1, "1d"),
    ],
)
def test_supported_timeframes_map_to_binance_intervals(
    timeframe: Timeframe, interval: str
) -> None:
    assert mapper.to_binance_interval(timeframe) == interval


@pytest.mark.parametrize(
    "timeframe", [Timeframe.M1, Timeframe.M30, Timeframe.W1]
)
def test_unsupported_timeframe_raises(timeframe: Timeframe) -> None:
    with pytest.raises(UnsupportedTimeframeError, match="does not support timeframe"):
        mapper.to_binance_interval(timeframe)


# --------------------------------------------------------------------------- #
# symbols
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("raw", "expected"), [("btcusdt", "BTCUSDT"), (" ethusdt ", "ETHUSDT")])
def test_normalize_symbol(raw: str, expected: str) -> None:
    assert mapper.normalize_symbol(raw) == expected


def test_normalize_symbol_rejects_blank() -> None:
    with pytest.raises(UnknownSymbolError):
        mapper.normalize_symbol("   ")


# --------------------------------------------------------------------------- #
# ticker price
# --------------------------------------------------------------------------- #


def test_map_price_quote(now: datetime) -> None:
    quote = mapper.map_price_quote(
        {"symbol": "BTCUSDT", "price": "64123.45000000"}, source=SOURCE, fetched_at=now
    )
    assert quote.symbol == "BTCUSDT"
    assert quote.price == Decimal("64123.45000000")
    assert isinstance(quote.price, Decimal)
    assert quote.timestamp == now
    assert quote.timestamp.tzinfo is not None
    assert quote.source == SOURCE


def test_map_price_quote_rejects_float_price(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="numeric string"):
        mapper.map_price_quote(
            {"symbol": "BTCUSDT", "price": 64123.45}, source=SOURCE, fetched_at=now
        )


def test_map_price_quote_rejects_missing_field(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="missing field 'price'"):
        mapper.map_price_quote({"symbol": "BTCUSDT"}, source=SOURCE, fetched_at=now)


def test_map_price_quote_rejects_non_numeric_price(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="is not a number"):
        mapper.map_price_quote(
            {"symbol": "BTCUSDT", "price": "n/a"}, source=SOURCE, fetched_at=now
        )


def test_map_price_quote_rejects_list_payload(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be an object"):
        mapper.map_price_quote([], source=SOURCE, fetched_at=now)


def test_map_price_quote_rejects_negative_price(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="violates PriceQuote"):
        mapper.map_price_quote(
            {"symbol": "BTCUSDT", "price": "-1"}, source=SOURCE, fetched_at=now
        )


# --------------------------------------------------------------------------- #
# book ticker
# --------------------------------------------------------------------------- #


def test_normalize_and_map_bid_ask(now: datetime) -> None:
    ticker = mapper.normalize_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "64120.10000000",
            "bidQty": "1.50000000",
            "askPrice": "64120.90000000",
            "askQty": "0.75000000",
        }
    )
    quote = mapper.to_bid_ask_quote(ticker, source=SOURCE, fetched_at=now)

    assert quote.bid == Decimal("64120.10000000")
    assert quote.ask == Decimal("64120.90000000")
    assert quote.bid_quantity == Decimal("1.50000000")
    assert quote.ask_quantity == Decimal("0.75000000")
    assert quote.spread == Decimal("0.80000000")
    assert quote.timestamp == now


def test_normalize_book_ticker_allows_missing_quantities() -> None:
    ticker = mapper.normalize_book_ticker(
        {"symbol": "BTCUSDT", "bidPrice": "1", "askPrice": "2"}
    )
    assert ticker.bid_quantity is None
    assert ticker.ask_quantity is None


def test_normalize_book_ticker_rejects_missing_price() -> None:
    with pytest.raises(InvalidProviderResponseError, match="missing field 'askPrice'"):
        mapper.normalize_book_ticker({"symbol": "BTCUSDT", "bidPrice": "1"})


def test_to_bid_ask_quote_rejects_crossed_quote(now: datetime) -> None:
    ticker = mapper.NormalizedBookTicker(
        symbol="BTCUSDT",
        bid=Decimal("101"),
        ask=Decimal("100"),
        bid_quantity=None,
        ask_quantity=None,
    )
    with pytest.raises(InvalidProviderResponseError, match="violates BidAskQuote"):
        mapper.to_bid_ask_quote(ticker, source=SOURCE, fetched_at=now)


# --------------------------------------------------------------------------- #
# klines
# --------------------------------------------------------------------------- #


def test_map_klines(now: datetime) -> None:
    candles = mapper.map_klines([_kline_row(now), _kline_row(now + timedelta(minutes=5))])

    assert len(candles) == 2
    first = candles[0]
    assert first.timestamp == now
    assert first.timestamp.tzinfo is UTC
    assert first.open == Decimal("100.10")
    assert first.high == Decimal("105.50")
    assert first.low == Decimal("99.90")
    assert first.close == Decimal("104.20")
    assert first.volume == Decimal("12.34567890")
    assert all(isinstance(value, Decimal) for value in (first.open, first.volume))
    assert candles[1].timestamp == now + timedelta(minutes=5)


def test_map_klines_preserves_provider_order(now: datetime) -> None:
    rows = [_kline_row(now + timedelta(minutes=5)), _kline_row(now)]
    candles = mapper.map_klines(rows)
    assert candles[0].timestamp > candles[1].timestamp


def test_map_klines_accepts_empty_payload() -> None:
    assert mapper.map_klines([]) == []


def test_map_klines_rejects_object_payload() -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be a list"):
        mapper.map_klines({"code": -1121})


def test_map_klines_rejects_short_row(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="expected at least 6"):
        mapper.map_klines([[_millis(now), "1", "2", "3"]])


def test_map_klines_rejects_non_numeric_field(now: datetime) -> None:
    row = _kline_row(now)
    row[2] = "not-a-price"
    with pytest.raises(InvalidProviderResponseError, match="is not a number"):
        mapper.map_klines([row])


def test_map_klines_rejects_bad_open_time() -> None:
    with pytest.raises(InvalidProviderResponseError, match="Unix millisecond"):
        mapper.map_klines([[None, "1", "2", "0.5", "1.5", "10"]])


def test_map_klines_rejects_inconsistent_candle(now: datetime) -> None:
    row = _kline_row(now)
    row[2] = "1.0"  # high below low
    with pytest.raises(InvalidProviderResponseError, match="violates OHLCVCandle"):
        mapper.map_klines([row])


# --------------------------------------------------------------------------- #
# exchange info
# --------------------------------------------------------------------------- #


def test_map_instrument_metadata(now: datetime) -> None:
    # fetched later than the payload's serverTime: server time must win
    metadata = mapper.map_instrument_metadata(
        _exchange_info(), symbol="BTCUSDT", source=SOURCE, fetched_at=now + timedelta(minutes=1)
    )

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
    assert metadata.source == SOURCE
    assert metadata.timestamp == now  # serverTime of the synthetic payload


def test_map_instrument_metadata_falls_back_to_min_notional_filter(now: datetime) -> None:
    payload = _exchange_info(
        filters=[
            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "stepSize": "1"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
        ]
    )
    metadata = mapper.map_instrument_metadata(
        payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now
    )
    assert metadata.min_notional == Decimal("10")
    assert metadata.price_precision == 1
    assert metadata.quantity_precision == 0
    assert metadata.min_quantity is None
    assert metadata.max_quantity is None


def test_map_instrument_metadata_maps_unknown_status(now: datetime) -> None:
    metadata = mapper.map_instrument_metadata(
        _exchange_info(status="SOMETHING_NEW"), symbol="BTCUSDT", source=SOURCE, fetched_at=now
    )
    assert metadata.status is InstrumentStatus.UNKNOWN


def test_map_instrument_metadata_maps_break_to_halted(now: datetime) -> None:
    metadata = mapper.map_instrument_metadata(
        _exchange_info(status="BREAK"), symbol="BTCUSDT", source=SOURCE, fetched_at=now
    )
    assert metadata.status is InstrumentStatus.HALTED


def test_map_instrument_metadata_unknown_symbol(now: datetime) -> None:
    with pytest.raises(UnknownSymbolError, match="does not describe symbol"):
        mapper.map_instrument_metadata(
            _exchange_info(), symbol="DOGEUSDT", source=SOURCE, fetched_at=now
        )


def test_map_instrument_metadata_requires_symbols_list(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="no 'symbols' list"):
        mapper.map_instrument_metadata(
            {"serverTime": 1}, symbol="BTCUSDT", source=SOURCE, fetched_at=now
        )


def test_map_instrument_metadata_requires_mandatory_filters(now: datetime) -> None:
    payload = _exchange_info(filters=[{"filterType": "PRICE_FILTER", "tickSize": "0.01"}])
    with pytest.raises(InvalidProviderResponseError, match="missing PRICE_FILTER or LOT_SIZE"):
        mapper.map_instrument_metadata(
            payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now
        )


def test_map_instrument_metadata_uses_fetch_time_without_server_time(now: datetime) -> None:
    payload = _exchange_info()
    del payload["serverTime"]
    metadata = mapper.map_instrument_metadata(
        payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now
    )
    assert metadata.timestamp == now


def test_extract_server_time(now: datetime) -> None:
    assert mapper.extract_server_time({"serverTime": _millis(now)}) == now
    assert mapper.extract_server_time({}) is None
    assert mapper.extract_server_time([]) is None
