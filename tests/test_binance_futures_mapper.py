"""Binance USD-M futures payload normalization.

All payloads here are hand-written synthetic shapes copied from the public API
documentation, not recorded market data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.market_data.exceptions import InvalidProviderResponseError, UnsupportedTimeframeError
from app.market_data.providers.binance.futures import mapper

SOURCE = "binance_futures:test"


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _futures_kline_row(open_time: datetime) -> list[object]:
    return [
        _millis(open_time),
        "100.10",
        "105.50",
        "99.90",
        "104.20",
        "12.5",  # volume
        _millis(open_time + timedelta(minutes=5)) - 1,
        "1300000.00",  # quoteAssetVolume
        800,  # numberOfTrades
        "7.5",  # takerBuyBaseAssetVolume
        "780000.00",  # takerBuyQuoteAssetVolume
        "0",
    ]


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
def test_supported_timeframes_map_to_futures_intervals(timeframe: Timeframe, interval: str) -> None:
    assert mapper.to_futures_interval(timeframe) == interval


@pytest.mark.parametrize("timeframe", [Timeframe.M1, Timeframe.M30, Timeframe.W1])
def test_unsupported_timeframe_raises(timeframe: Timeframe) -> None:
    with pytest.raises(UnsupportedTimeframeError, match="does not support timeframe"):
        mapper.to_futures_interval(timeframe)


# --------------------------------------------------------------------------- #
# funding interval discovery
# --------------------------------------------------------------------------- #


def test_extract_funding_interval_hours_finds_symbol() -> None:
    payload = [{"symbol": "BTCUSDT", "fundingIntervalHours": 4}, {"symbol": "ETHUSDT", "fundingIntervalHours": 8}]
    assert mapper.extract_funding_interval_hours(payload, "BTCUSDT") == 4


def test_extract_funding_interval_hours_none_when_symbol_absent() -> None:
    payload = [{"symbol": "ETHUSDT", "fundingIntervalHours": 8}]
    assert mapper.extract_funding_interval_hours(payload, "BTCUSDT") is None


def test_extract_funding_interval_hours_none_for_empty_list() -> None:
    assert mapper.extract_funding_interval_hours([], "BTCUSDT") is None


def test_extract_funding_interval_hours_rejects_non_list() -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be a list"):
        mapper.extract_funding_interval_hours({"symbol": "BTCUSDT"}, "BTCUSDT")


@pytest.mark.parametrize("hours", [0, -1, "8", None])
def test_extract_funding_interval_hours_rejects_invalid_value(hours: object) -> None:
    payload = [{"symbol": "BTCUSDT", "fundingIntervalHours": hours}]
    with pytest.raises(InvalidProviderResponseError, match="invalid fundingIntervalHours"):
        mapper.extract_funding_interval_hours(payload, "BTCUSDT")


# --------------------------------------------------------------------------- #
# funding rate
# --------------------------------------------------------------------------- #


def _premium_index(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "symbol": "BTCUSDT",
        "markPrice": "64100.50000000",
        "indexPrice": "64099.10000000",
        "lastFundingRate": "-0.00010000",
        "nextFundingTime": 0,
        "time": 0,
    }
    body.update(overrides)
    return body


def test_map_funding_rate(now: datetime) -> None:
    payload = _premium_index(nextFundingTime=_millis(now + timedelta(hours=4)), time=_millis(now))
    funding = mapper.map_funding_rate(
        payload, funding_interval_hours=4, source=SOURCE, fetched_at=now + timedelta(seconds=1)
    )

    assert funding.symbol == "BTCUSDT"
    assert funding.contract_type is ContractType.PERPETUAL
    assert funding.funding_rate == Decimal("-0.00010000")
    assert funding.funding_interval_hours == 4
    assert funding.mark_price == Decimal("64100.50000000")
    assert funding.index_price == Decimal("64099.10000000")
    assert funding.next_funding_time == now + timedelta(hours=4)
    assert funding.timestamp == now
    assert funding.source == SOURCE


def test_map_funding_rate_allows_negative_rate(now: datetime) -> None:
    funding = mapper.map_funding_rate(
        _premium_index(lastFundingRate="-0.00500000", time=_millis(now)),
        funding_interval_hours=None,
        source=SOURCE,
        fetched_at=now,
    )
    assert funding.funding_rate == Decimal("-0.00500000")


def test_map_funding_rate_missing_interval_is_none(now: datetime) -> None:
    funding = mapper.map_funding_rate(
        _premium_index(time=_millis(now)), funding_interval_hours=None, source=SOURCE, fetched_at=now
    )
    assert funding.funding_interval_hours is None


def test_map_funding_rate_zero_next_funding_time_is_none(now: datetime) -> None:
    funding = mapper.map_funding_rate(
        _premium_index(nextFundingTime=0, time=_millis(now)),
        funding_interval_hours=None,
        source=SOURCE,
        fetched_at=now,
    )
    assert funding.next_funding_time is None


def test_map_funding_rate_falls_back_to_fetch_time_without_time_field(now: datetime) -> None:
    payload = _premium_index(time=0)
    funding = mapper.map_funding_rate(
        payload, funding_interval_hours=None, source=SOURCE, fetched_at=now
    )
    assert funding.timestamp == now


def test_map_funding_rate_rejects_missing_mark_price(now: datetime) -> None:
    payload = _premium_index(time=_millis(now))
    del payload["markPrice"]
    with pytest.raises(InvalidProviderResponseError, match="missing field 'markPrice'"):
        mapper.map_funding_rate(payload, funding_interval_hours=None, source=SOURCE, fetched_at=now)


# --------------------------------------------------------------------------- #
# open interest
# --------------------------------------------------------------------------- #


def test_map_open_interest(now: datetime) -> None:
    payload = {"symbol": "BTCUSDT", "openInterest": "12345.60000000", "time": _millis(now)}
    open_interest = mapper.map_open_interest(payload, source=SOURCE, fetched_at=now + timedelta(seconds=5))

    assert open_interest.symbol == "BTCUSDT"
    assert open_interest.contract_type is ContractType.PERPETUAL
    assert open_interest.open_interest == Decimal("12345.60000000")
    assert open_interest.timestamp == now
    assert open_interest.source == SOURCE


def test_map_open_interest_falls_back_to_fetch_time(now: datetime) -> None:
    payload = {"symbol": "BTCUSDT", "openInterest": "1"}
    open_interest = mapper.map_open_interest(payload, source=SOURCE, fetched_at=now)
    assert open_interest.timestamp == now


def test_map_open_interest_rejects_negative_value(now: datetime) -> None:
    payload = {"symbol": "BTCUSDT", "openInterest": "-1", "time": _millis(now)}
    with pytest.raises(InvalidProviderResponseError, match="violates OpenInterest"):
        mapper.map_open_interest(payload, source=SOURCE, fetched_at=now)


# --------------------------------------------------------------------------- #
# taker flow
# --------------------------------------------------------------------------- #


def test_map_taker_flow(now: datetime) -> None:
    rows = [_futures_kline_row(now), _futures_kline_row(now + timedelta(minutes=5))]
    snapshots = mapper.map_taker_flow(rows, symbol="BTCUSDT", timeframe=Timeframe.M5, source=SOURCE)

    assert len(snapshots) == 2
    first = snapshots[0]
    assert first.symbol == "BTCUSDT"
    assert first.contract_type is ContractType.PERPETUAL
    assert first.timeframe is Timeframe.M5
    assert first.timestamp == now
    assert first.buy_volume == Decimal("7.5")
    assert first.sell_volume == Decimal("12.5") - Decimal("7.5")
    assert first.buy_quote_volume == Decimal("780000.00")
    assert first.total_volume == Decimal("12.5")
    assert first.delta == Decimal("7.5") - (Decimal("12.5") - Decimal("7.5"))
    assert 0.0 <= first.buy_ratio <= 1.0


def test_map_taker_flow_sell_volume_is_total_minus_taker_buy(now: datetime) -> None:
    row = _futures_kline_row(now)
    row[5] = "20"  # total volume
    row[9] = "8"  # taker buy volume
    snapshot = mapper.map_taker_flow([row], symbol="BTCUSDT", timeframe=Timeframe.M5, source=SOURCE)[0]
    assert snapshot.buy_volume == Decimal("8")
    assert snapshot.sell_volume == Decimal("12")


def test_map_taker_flow_rejects_non_list_payload() -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be a list"):
        mapper.map_taker_flow({"code": -1121}, symbol="BTCUSDT", timeframe=Timeframe.M5, source=SOURCE)


def test_map_taker_flow_rejects_short_row(now: datetime) -> None:
    with pytest.raises(InvalidProviderResponseError, match="expected at least 11"):
        mapper.map_taker_flow(
            [[_millis(now), "1", "2", "3", "4", "5"]],
            symbol="BTCUSDT",
            timeframe=Timeframe.M5,
            source=SOURCE,
        )


def test_map_taker_flow_accepts_empty_payload() -> None:
    assert mapper.map_taker_flow([], symbol="BTCUSDT", timeframe=Timeframe.M5, source=SOURCE) == []


def test_map_taker_flow_rejects_non_numeric_volume(now: datetime) -> None:
    row = _futures_kline_row(now)
    row[5] = "not-a-number"
    with pytest.raises(InvalidProviderResponseError, match="is not a number"):
        mapper.map_taker_flow([row], symbol="BTCUSDT", timeframe=Timeframe.M5, source=SOURCE)


# --------------------------------------------------------------------------- #
# order book
# --------------------------------------------------------------------------- #


def test_map_order_book_snapshot(now: datetime) -> None:
    payload = {
        "lastUpdateId": 123456,
        "E": _millis(now),
        "T": _millis(now),
        "bids": [["64000.00", "1.500"], ["63999.00", "2.000"]],
        "asks": [["64001.00", "0.750"]],
    }
    snapshot = mapper.map_order_book_snapshot(
        payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now + timedelta(seconds=1)
    )

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.contract_type is ContractType.PERPETUAL
    assert snapshot.last_update_id == 123456
    assert snapshot.bids[0].price == Decimal("64000.00")
    assert snapshot.bids[0].quantity == Decimal("1.500")
    assert snapshot.asks[0].price == Decimal("64001.00")
    assert snapshot.timestamp == now


def test_map_order_book_snapshot_falls_back_to_fetch_time(now: datetime) -> None:
    payload = {"lastUpdateId": 1, "bids": [], "asks": []}
    snapshot = mapper.map_order_book_snapshot(payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now)
    assert snapshot.timestamp == now


def test_map_order_book_snapshot_allows_empty_sides(now: datetime) -> None:
    payload = {"lastUpdateId": 1, "bids": [], "asks": []}
    snapshot = mapper.map_order_book_snapshot(payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now)
    assert snapshot.bids == []
    assert snapshot.asks == []


def test_map_order_book_snapshot_rejects_missing_last_update_id(now: datetime) -> None:
    payload = {"bids": [], "asks": []}
    with pytest.raises(InvalidProviderResponseError, match="invalid lastUpdateId"):
        mapper.map_order_book_snapshot(payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now)


def test_map_order_book_snapshot_rejects_crossed_book(now: datetime) -> None:
    payload = {"lastUpdateId": 1, "bids": [["101", "1"]], "asks": [["100", "1"]]}
    with pytest.raises(InvalidProviderResponseError, match="violates OrderBookSnapshot"):
        mapper.map_order_book_snapshot(payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now)


def test_map_order_book_snapshot_rejects_malformed_level(now: datetime) -> None:
    payload = {"lastUpdateId": 1, "bids": [["100"]], "asks": []}
    with pytest.raises(InvalidProviderResponseError, match="price, quantity"):
        mapper.map_order_book_snapshot(payload, symbol="BTCUSDT", source=SOURCE, fetched_at=now)
