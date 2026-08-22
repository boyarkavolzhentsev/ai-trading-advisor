"""OHLCVCandle validation rules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.models import OHLCVCandle


def _candle(now: datetime, **overrides: object) -> OHLCVCandle:
    fields: dict[str, object] = {
        "timestamp": now,
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("99"),
        "close": Decimal("104"),
        "volume": Decimal("1000"),
    }
    fields.update(overrides)
    return OHLCVCandle(**fields)


def test_valid_candle(now: datetime) -> None:
    candle = _candle(now)
    assert candle.high >= candle.low
    assert candle.timestamp == now


def test_high_below_low_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="high must be greater than or equal"):
        _candle(now, high=Decimal("98"), open=Decimal("98"), close=Decimal("98"))


def test_negative_price_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _candle(now, low=Decimal("-1"))


def test_negative_volume_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _candle(now, volume=Decimal("-1"))


def test_close_outside_range_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="close must be within"):
        _candle(now, close=Decimal("110"))


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _candle(datetime(2026, 1, 2, 12, 0))


def test_candle_is_immutable(now: datetime) -> None:
    candle = _candle(now)
    with pytest.raises(ValidationError):
        candle.close = Decimal("101")


def test_unknown_field_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _candle(now, vwap=Decimal("101"))
