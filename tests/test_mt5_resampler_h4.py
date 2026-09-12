"""Pure H1 -> H4 resampling (``app.market_data.providers.mt5.resampler``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.models.candle import OHLCVCandle
from app.market_data.providers.mt5.resampler import resample_h4

_BUCKET = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)  # a canonical 08:00 UTC H4 bucket start


def _candle(hour_offset: int, *, open: str, high: str, low: str, close: str, volume: str) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=_BUCKET + timedelta(hours=hour_offset),
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def _flat_candle(hour_offset: int) -> OHLCVCandle:
    return _candle(hour_offset, open="100", high="101", low="99", close="100", volume="10")


def test_exactly_4_h1_candles_produce_one_h4_candle() -> None:
    candles = [
        _candle(0, open="100", high="105", low="99", close="102", volume="10"),
        _candle(1, open="102", high="108", low="101", close="107", volume="20"),
        _candle(2, open="107", high="110", low="103", close="104", volume="15"),
        _candle(3, open="104", high="106", low="98", close="105", volume="5"),
    ]
    assert len(resample_h4(candles)) == 1


def test_h4_aggregation_is_correct() -> None:
    candles = [
        _candle(0, open="100", high="105", low="99", close="102", volume="10"),
        _candle(1, open="102", high="108", low="101", close="107", volume="20"),
        _candle(2, open="107", high="110", low="103", close="104", volume="15"),
        _candle(3, open="104", high="106", low="98", close="105", volume="5"),
    ]
    [h4] = resample_h4(candles)
    assert h4.open == Decimal("100")
    assert h4.high == Decimal("110")
    assert h4.low == Decimal("98")
    assert h4.close == Decimal("105")


def test_h4_volume_is_summed() -> None:
    candles = [_flat_candle(i) for i in range(4)]
    [h4] = resample_h4(candles)
    assert h4.volume == Decimal("40")


def test_h4_timestamp_is_utc_bucket_start() -> None:
    candles = [_flat_candle(i) for i in range(4)]
    [h4] = resample_h4(candles)
    assert h4.timestamp == _BUCKET


def test_3_of_4_produces_no_candle() -> None:
    candles = [_flat_candle(i) for i in (0, 1, 2)]
    assert resample_h4(candles) == []


def test_missing_middle_h1_produces_no_candle() -> None:
    candles = [_flat_candle(i) for i in (0, 1, 3)]
    assert resample_h4(candles) == []


def test_duplicate_timestamp_produces_no_candle() -> None:
    candles = [_flat_candle(0) for _ in range(4)]
    assert resample_h4(candles) == []


def test_multiple_consecutive_h4_buckets() -> None:
    first_bucket = [_flat_candle(i) for i in range(4)]
    second_bucket = [_flat_candle(4 + i) for i in range(4)]
    result = resample_h4(first_bucket + second_bucket)
    assert len(result) == 2
    assert result[0].timestamp == _BUCKET
    assert result[1].timestamp == _BUCKET + timedelta(hours=4)


def test_incomplete_leading_bucket_is_ignored_while_complete_bucket_still_produced() -> None:
    incomplete_leading = [_flat_candle(-2), _flat_candle(-1)]  # only 2 of the previous bucket's 4 members
    complete_bucket = [_flat_candle(i) for i in range(4)]
    result = resample_h4(incomplete_leading + complete_bucket)
    assert len(result) == 1
    assert result[0].timestamp == _BUCKET


def test_incomplete_trailing_bucket_is_ignored_while_complete_bucket_still_produced() -> None:
    complete_bucket = [_flat_candle(i) for i in range(4)]
    incomplete_trailing = [_flat_candle(4)]  # only 1 of the next bucket's 4 members
    result = resample_h4(complete_bucket + incomplete_trailing)
    assert len(result) == 1
    assert result[0].timestamp == _BUCKET
