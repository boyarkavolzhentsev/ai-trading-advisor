"""TradeSetup contract: execution window and entry specification."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import SIGNAL_EXECUTION_WINDOW
from app.core.models import EntryZone, TradeSetup


def _setup(now: datetime, **overrides: object) -> TradeSetup:
    fields: dict[str, object] = {
        "symbol": "TEST",
        "market": "FX",
        "direction": "LONG",
        "signal_time": now,
        "valid_until": now + SIGNAL_EXECUTION_WINDOW,
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("99"),
        "take_profit_levels": [Decimal("102"), Decimal("104")],
        "confidence": 0.6,
    }
    fields.update(overrides)
    return TradeSetup(**fields)


def test_execution_window_is_five_minutes() -> None:
    assert SIGNAL_EXECUTION_WINDOW == timedelta(minutes=5)


def test_valid_setup(now: datetime) -> None:
    setup = _setup(now)
    assert setup.valid_until - setup.signal_time == SIGNAL_EXECUTION_WINDOW
    assert setup.risk_reward is None


def test_valid_until_before_signal_time_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="valid_until must be after signal_time"):
        _setup(now, valid_until=now - timedelta(minutes=1))


def test_valid_until_equal_to_signal_time_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="valid_until must be after signal_time"):
        _setup(now, valid_until=now)


def test_entry_zone_alternative_is_accepted(now: datetime) -> None:
    setup = _setup(
        now,
        entry_price=None,
        entry_zone=EntryZone(low=Decimal("99.8"), high=Decimal("100.2")),
    )
    assert setup.entry_zone is not None
    assert setup.entry_price is None


def test_both_entry_forms_are_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="exactly one of entry_price"):
        _setup(
            now,
            entry_zone=EntryZone(low=Decimal("99.8"), high=Decimal("100.2")),
        )


def test_missing_entry_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError, match="exactly one of entry_price"):
        _setup(now, entry_price=None)


def test_inverted_entry_zone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="entry zone high"):
        EntryZone(low=Decimal("101"), high=Decimal("100"))


def test_negative_stop_loss_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _setup(now, stop_loss=Decimal("-1"))


def test_negative_risk_reward_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _setup(now, risk_reward=-2.0)
