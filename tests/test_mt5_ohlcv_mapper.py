"""Raw MT5 rate -> ``OHLCVCandle`` mapping
(``app.market_data.providers.mt5.mapper``)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.models.mt5_rate import MT5RawRate
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.providers.mt5.mapper import map_mt5_rate, map_mt5_rates

_SERVER_TIMEZONE = "Europe/Bucharest"


def _raw_epoch_for_wall_clock_digits(naive_local: datetime) -> int:
    return int(naive_local.replace(tzinfo=UTC).timestamp())


def _raw_rate(
    *,
    naive_local: datetime = datetime(2026, 1, 1, 15, 0, 0),
    open: Decimal = Decimal("100"),
    high: Decimal = Decimal("101"),
    low: Decimal = Decimal("99"),
    close: Decimal = Decimal("100.5"),
    tick_volume: int = 500,
    real_volume: int = 0,
) -> MT5RawRate:
    return MT5RawRate(
        epoch_seconds=_raw_epoch_for_wall_clock_digits(naive_local),
        open=open,
        high=high,
        low=low,
        close=close,
        tick_volume=tick_volume,
        real_volume=real_volume,
    )


def test_timestamp_normalizes_to_canonical_utc() -> None:
    raw = _raw_rate(naive_local=datetime(2026, 1, 1, 15, 0, 0))
    candle = map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)
    assert candle.timestamp == datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)


def test_tick_volume_maps_to_candle_volume() -> None:
    raw = _raw_rate(tick_volume=777, real_volume=999999)
    candle = map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)
    assert candle.volume == Decimal("777")


def test_real_volume_is_never_read() -> None:
    low_real = _raw_rate(tick_volume=500, real_volume=0)
    high_real = _raw_rate(tick_volume=500, real_volume=123456789)
    low_candle = map_mt5_rate(low_real, server_timezone=_SERVER_TIMEZONE)
    high_candle = map_mt5_rate(high_real, server_timezone=_SERVER_TIMEZONE)
    assert low_candle.volume == high_candle.volume == Decimal("500")


def test_ohlc_prices_pass_through_as_decimal() -> None:
    raw = _raw_rate(open=Decimal("100.25"), high=Decimal("101.75"), low=Decimal("99.10"), close=Decimal("100.60"))
    candle = map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)
    assert candle.open == Decimal("100.25")
    assert candle.high == Decimal("101.75")
    assert candle.low == Decimal("99.10")
    assert candle.close == Decimal("100.60")


def test_invalid_ohlc_consistency_is_rejected() -> None:
    raw = _raw_rate(open=Decimal("100"), high=Decimal("99"), low=Decimal("101"), close=Decimal("100"))  # high < low
    with pytest.raises(InvalidProviderResponseError):
        map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_zero_price_is_rejected(field: str) -> None:
    kwargs: dict[str, Decimal] = {"open": Decimal("100"), "high": Decimal("101"), "low": Decimal("99"), "close": Decimal("100")}
    kwargs[field] = Decimal("0")
    raw = _raw_rate(**kwargs)
    with pytest.raises(InvalidProviderResponseError):
        map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_negative_price_is_rejected(field: str) -> None:
    kwargs: dict[str, Decimal] = {"open": Decimal("100"), "high": Decimal("101"), "low": Decimal("99"), "close": Decimal("100")}
    kwargs[field] = Decimal("-1")
    raw = _raw_rate(**kwargs)
    with pytest.raises(InvalidProviderResponseError):
        map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)


def test_negative_tick_volume_is_rejected() -> None:
    raw = _raw_rate(tick_volume=-1)
    with pytest.raises(InvalidProviderResponseError):
        map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)


def test_dst_gap_timestamp_is_rejected_as_invalid_provider_response() -> None:
    raw = _raw_rate(naive_local=datetime(2026, 3, 29, 3, 30, 0))  # Europe/Bucharest spring-forward gap
    with pytest.raises(InvalidProviderResponseError):
        map_mt5_rate(raw, server_timezone=_SERVER_TIMEZONE)


def test_map_mt5_rates_preserves_input_order() -> None:
    raws = [
        _raw_rate(naive_local=datetime(2026, 1, 1, 13, 0, 0)),
        _raw_rate(naive_local=datetime(2026, 1, 1, 14, 0, 0)),
        _raw_rate(naive_local=datetime(2026, 1, 1, 15, 0, 0)),
    ]
    candles = map_mt5_rates(raws, server_timezone=_SERVER_TIMEZONE)
    assert [candle.timestamp for candle in candles] == sorted(candle.timestamp for candle in candles)
