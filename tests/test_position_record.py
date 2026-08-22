"""PositionRecord lifecycle contract."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import SIGNAL_EXECUTION_WINDOW
from app.core.enums import MarketType, TradeDirection, TradeStatus
from app.core.models import PositionRecord


def _record(now: datetime, **overrides: object) -> PositionRecord:
    fields: dict[str, object] = {
        "trade_id": "T-1",
        "symbol": "TEST",
        "market": MarketType.FX,
        "direction": TradeDirection.LONG,
        "signal_time": now,
        "valid_until": now + SIGNAL_EXECUTION_WINDOW,
        "planned_entry": Decimal("100"),
        "stop_loss": Decimal("99"),
        "take_profit_levels": [Decimal("102")],
    }
    fields.update(overrides)
    return PositionRecord(**fields)


def test_broker_fields_are_optional_at_creation(now: datetime) -> None:
    record = _record(now)
    assert record.status is TradeStatus.PENDING
    assert record.actual_entry is None
    assert record.actual_entry_time is None
    assert record.exit_price is None
    assert record.exit_time is None
    assert record.pnl is None
    assert record.pnl_percent is None


def test_broker_fields_can_be_filled_later(now: datetime) -> None:
    record = _record(now)
    record.status = TradeStatus.FILLED
    record.actual_entry = Decimal("100.05")
    record.actual_entry_time = now + timedelta(minutes=1)
    record.exit_price = Decimal("102")
    record.exit_time = now + timedelta(hours=3)
    record.pnl = Decimal("-25.5")
    record.pnl_percent = Decimal("-0.026")

    assert record.status is TradeStatus.FILLED
    assert record.actual_entry == Decimal("100.05")
    assert record.pnl == Decimal("-25.5")


def test_unfilled_recommendation_can_be_recorded(now: datetime) -> None:
    record = _record(now, status=TradeStatus.NOT_FILLED)
    assert record.status is TradeStatus.NOT_FILLED
    assert record.actual_entry is None


def test_valid_until_must_be_after_signal_time(now: datetime) -> None:
    with pytest.raises(ValidationError, match="valid_until must be after signal_time"):
        _record(now, valid_until=now)


def test_exit_before_entry_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="exit_time cannot be before"):
        _record(
            now,
            actual_entry=Decimal("100"),
            actual_entry_time=now + timedelta(minutes=2),
            exit_price=Decimal("101"),
            exit_time=now + timedelta(minutes=1),
        )


def test_invalid_status_assignment_is_rejected(now: datetime) -> None:
    record = _record(now)
    with pytest.raises(ValidationError):
        record.status = "PARTIALLY_FILLED"
