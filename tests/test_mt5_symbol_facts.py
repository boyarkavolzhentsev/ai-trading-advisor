"""Stage 10C symbol facts: ``MT5SymbolFacts`` model and
``MT5Client.symbol_facts()`` adapter behavior - missing symbol/tick data,
trade-mode mapping incl. UNKNOWN, Decimal normalization, no raw MT5 object
leakage."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.mt5.client import MT5Client
from app.mt5.errors import MT5NotInitializedError
from tests.mt5_position_support import default_raw_symbol_info, default_raw_tick, default_symbol_facts
from tests.mt5_support import FakeRawMT5Module


# --- MT5SymbolFacts model ---


def test_symbol_facts_permissive_tick_size() -> None:
    """Structurally permissive - invalid values are business-rule concerns
    for app.mt5.risk/app.mt5.sizing, not construction errors."""
    facts = default_symbol_facts(trade_tick_size=Decimal("0"))
    assert facts.trade_tick_size == Decimal("0")


def test_symbol_facts_frozen() -> None:
    facts = default_symbol_facts()
    with pytest.raises(ValidationError):
        facts.bid = Decimal("1")


def test_symbol_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5SymbolFacts(
            as_of=default_symbol_facts().as_of,
            symbol="EURUSD",
            trade_tick_size=Decimal("0.00001"),
            trade_tick_value_loss=Decimal("1"),
            point=Decimal("0.00001"),
            volume_min=Decimal("0.01"),
            volume_max=Decimal("100"),
            volume_step=Decimal("0.01"),
            trade_stops_level=0,
            trade_mode=MT5SymbolTradeMode.FULL,
            bid=Decimal("1"),
            ask=Decimal("1"),
            digits=5,  # genuinely unknown/excluded field - "point" is itself a real field now
        )


def test_symbol_facts_has_no_speculative_fields() -> None:
    """``point`` is deliberately NOT in this exclusion list (corrective
    review, "MT5 BROKER STOP-LEVEL SEMANTICS") - it is a real, required
    field, distinct from ``trade_tick_size``, needed for broker minimum-
    stop-distance validation."""
    for field in ("digits", "trade_tick_value_profit", "contract_size", "currency", "trade_freeze_level"):
        assert field not in MT5SymbolFacts.model_fields
    assert "point" in MT5SymbolFacts.model_fields


# --- MT5Client.symbol_facts() ---


def test_symbol_facts_missing_symbol_info_returns_none() -> None:
    raw = FakeRawMT5Module(symbol_info_result=None, symbol_tick_result=default_raw_tick())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert client.symbol_facts("EURUSD") is None


def test_symbol_facts_missing_tick_returns_none() -> None:
    raw = FakeRawMT5Module(symbol_info_result=default_raw_symbol_info(), symbol_tick_result=None)
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert client.symbol_facts("EURUSD") is None


def test_symbol_facts_normalizes_all_fields() -> None:
    raw = FakeRawMT5Module(
        symbol_info_result=default_raw_symbol_info(
            trade_tick_size=0.00001,
            trade_tick_value_loss=1.25,
            point=0.00001,
            volume_min=0.01,
            volume_max=50.0,
            volume_step=0.01,
            trade_stops_level=10,
        ),
        symbol_tick_result=default_raw_tick(bid=1.2345, ask=1.2347),
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.symbol_facts("EURUSD")
    assert facts is not None
    assert facts.trade_tick_size == Decimal("0.00001")
    assert facts.trade_tick_value_loss == Decimal("1.25")
    assert facts.point == Decimal("0.00001")
    assert facts.volume_min == Decimal("0.01")
    assert facts.volume_max == Decimal("50.0")
    assert facts.volume_step == Decimal("0.01")
    assert facts.trade_stops_level == 10
    assert facts.bid == Decimal("1.2345")
    assert facts.ask == Decimal("1.2347")
    assert isinstance(facts, MT5SymbolFacts)


def test_symbol_facts_maps_point_verbatim_and_distinct_from_tick_size() -> None:
    """MT5 client mapping test (corrective review, "MT5 BROKER STOP-LEVEL
    SEMANTICS"): MetaTrader5 symbol_info.point -> MT5SymbolFacts.point,
    verbatim Decimal conversion, using a fixture where point and
    trade_tick_size deliberately differ - proving the client never derives
    one from the other. No live MT5 call."""
    raw = FakeRawMT5Module(
        symbol_info_result=default_raw_symbol_info(trade_tick_size=0.10, point=0.01),
        symbol_tick_result=default_raw_tick(),
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.symbol_facts("EURUSD")
    assert facts is not None
    assert facts.point == Decimal("0.01")
    assert facts.trade_tick_size == Decimal("0.10")
    assert facts.point != facts.trade_tick_size


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (0, MT5SymbolTradeMode.DISABLED),
        (1, MT5SymbolTradeMode.LONG_ONLY),
        (2, MT5SymbolTradeMode.SHORT_ONLY),
        (3, MT5SymbolTradeMode.CLOSE_ONLY),
        (4, MT5SymbolTradeMode.FULL),
        (99, MT5SymbolTradeMode.UNKNOWN),
    ],
)
def test_symbol_facts_trade_mode_mapping(raw_value: int, expected: MT5SymbolTradeMode) -> None:
    raw = FakeRawMT5Module(
        symbol_info_result=default_raw_symbol_info(trade_mode=raw_value),
        symbol_tick_result=default_raw_tick(),
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.symbol_facts("EURUSD")
    assert facts is not None
    assert facts.trade_mode is expected


def test_symbol_facts_unavailable_when_not_connected() -> None:
    from tests.mt5_support import default_terminal_info

    raw = FakeRawMT5Module(
        terminal_info=default_terminal_info(connected=False),
        symbol_info_result=default_raw_symbol_info(),
        symbol_tick_result=default_raw_tick(),
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert client.symbol_facts("EURUSD") is None


def test_symbol_facts_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.symbol_facts("EURUSD")
