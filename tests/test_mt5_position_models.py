"""Stage 10C position normalization: ``MT5Position`` model validation and
``MT5Client.positions()`` adapter behavior - BUY/SELL mapping, unknown-side
fail-closed, ``Decimal`` normalization, ``sl == 0`` -> ``None``, no
symbol/magic/family filtering, no raw MT5 object leakage."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.order import OrderSide
from app.core.models.mt5_position import MT5Position
from app.mt5.client import MT5Client
from app.mt5.errors import MT5NotInitializedError
from tests.mt5_position_support import NOW, default_position, default_raw_position
from tests.mt5_support import FakeRawMT5Module


# --- MT5Position model ---


def test_position_rejects_non_positive_ticket() -> None:
    with pytest.raises(ValidationError):
        default_position(ticket=0)


def test_position_rejects_non_positive_volume() -> None:
    with pytest.raises(ValidationError):
        default_position(volume=Decimal("0"))


def test_position_rejects_non_positive_price_open() -> None:
    with pytest.raises(ValidationError):
        default_position(price_open=Decimal("0"))


def test_position_accepts_zero_price_current() -> None:
    """price_current is a permissive, business-rule-checked live fact -
    never a construction-time rejection (see app.mt5.risk)."""
    position = default_position(price_current=Decimal("0"))
    assert position.price_current == Decimal("0")


def test_position_stop_loss_may_be_none() -> None:
    position = default_position(stop_loss=None)
    assert position.stop_loss is None


def test_position_frozen() -> None:
    position = default_position()
    with pytest.raises(ValidationError):
        position.volume = Decimal("2")


def test_position_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5Position(
            as_of=NOW,
            ticket=1,
            symbol="EURUSD",
            side=OrderSide.BUY,
            volume=Decimal("1"),
            price_open=Decimal("100"),
            price_current=Decimal("100"),
            stop_loss=Decimal("95"),
            magic=12345,
        )


def test_position_has_no_speculative_fields() -> None:
    for field in ("tp", "profit", "swap", "magic", "comment", "time", "time_msc", "reason"):
        assert field not in MT5Position.model_fields


# --- MT5Client.positions() ---


def test_positions_buy_mapping() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(type=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "OK"
    assert len(positions) == 1
    assert positions[0].side is OrderSide.BUY


def test_positions_sell_mapping() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(type=1),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "OK"
    assert positions[0].side is OrderSide.SELL


def test_positions_unknown_side_fails_closed() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(type=99),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "UNMAPPABLE_POSITION_SIDE"
    assert positions == ()


def test_positions_no_open_positions_is_ok_empty() -> None:
    raw = FakeRawMT5Module(positions=())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "OK"
    assert positions == ()


def test_positions_returns_all_account_positions_unfiltered() -> None:
    raw = FakeRawMT5Module(
        positions=(
            default_raw_position(ticket=1, symbol="EURUSD"),
            default_raw_position(ticket=2, symbol="XAUUSD"),
            default_raw_position(ticket=3, symbol="BTCUSD"),
        )
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "OK"
    assert {position.ticket for position in positions} == {1, 2, 3}
    assert {position.symbol for position in positions} == {"EURUSD", "XAUUSD", "BTCUSD"}


def test_positions_sl_zero_normalizes_to_none() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(sl=0.0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, positions = client.positions()
    assert positions[0].stop_loss is None


def test_positions_sl_nonzero_normalizes_to_decimal() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(sl=95.25),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, positions = client.positions()
    assert positions[0].stop_loss == Decimal("95.25")


def test_positions_decimal_normalization_avoids_float_repr_artifacts() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(volume=0.1, price_open=125.30, price_current=126.7),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, positions = client.positions()
    position = positions[0]
    assert position.volume == Decimal("0.1")
    assert position.price_open == Decimal("125.3")
    assert position.price_current == Decimal("126.7")


def test_positions_raw_object_never_returned() -> None:
    raw = FakeRawMT5Module(positions=(default_raw_position(),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, positions = client.positions()
    assert all(isinstance(position, MT5Position) for position in positions)


def test_positions_unavailable_when_terminal_disconnected() -> None:
    from tests.mt5_support import default_terminal_info

    raw = FakeRawMT5Module(terminal_info=default_terminal_info(connected=False))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "UNAVAILABLE"
    assert positions == ()


def test_positions_unavailable_never_fabricates_confirmed_empty() -> None:
    """A raw positions_get() -> None (query failure) must not be
    indistinguishable from a genuinely confirmed zero-position account."""
    raw = FakeRawMT5Module(positions=None)
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, positions = client.positions()
    assert status == "UNAVAILABLE"
    assert positions == ()


def test_positions_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.positions()


def test_positions_after_shutdown_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    with pytest.raises(MT5NotInitializedError):
        client.positions()
