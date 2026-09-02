"""Stage 10C pure broker-aware final sizing: volume-grid flooring (the
approved volume_min-anchored algorithm), reference-price rule, tradability,
tick economics, actual-risk re-verification - exact Decimal throughout."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.enums.trade import TradeDirection
from app.core.models.mt5_sizing import MT5BrokerSizingRequest
from app.mt5.sizing import compute_broker_sizing, floor_volume_to_step
from tests.mt5_position_support import NOW, default_symbol_facts


# --- Volume grid: required regressions ---


@pytest.mark.parametrize(
    ("volume_min", "volume_step", "raw", "expected"),
    [
        (Decimal("0.01"), Decimal("0.01"), Decimal("0.037"), Decimal("0.03")),
        (Decimal("1"), Decimal("1"), Decimal("3.7"), Decimal("3")),
        (Decimal("0.03"), Decimal("0.02"), Decimal("0.03"), Decimal("0.03")),
        (Decimal("0.03"), Decimal("0.02"), Decimal("0.04"), Decimal("0.03")),
        (Decimal("0.03"), Decimal("0.02"), Decimal("0.05"), Decimal("0.05")),
        (Decimal("0.03"), Decimal("0.02"), Decimal("0.08"), Decimal("0.07")),
        (Decimal("0.03"), Decimal("0.02"), Decimal("0.09"), Decimal("0.09")),
    ],
)
def test_volume_grid_regressions(volume_min: Decimal, volume_step: Decimal, raw: Decimal, expected: Decimal) -> None:
    result = floor_volume_to_step(raw, volume_min, Decimal("1000"), volume_step)
    assert result == expected


def test_volume_grid_below_minimum() -> None:
    result = floor_volume_to_step(Decimal("0.02"), Decimal("0.03"), Decimal("1000"), Decimal("0.02"))
    assert result is None


def test_volume_grid_never_produces_08_or_06() -> None:
    result = floor_volume_to_step(Decimal("0.08"), Decimal("0.03"), Decimal("1000"), Decimal("0.02"))
    assert result != Decimal("0.08")
    assert result != Decimal("0.06")
    assert result == Decimal("0.07")


def test_volume_grid_never_rounds_up() -> None:
    result = floor_volume_to_step(Decimal("0.089999"), Decimal("0.03"), Decimal("1000"), Decimal("0.02"))
    assert result is not None
    assert result <= Decimal("0.089999")


def test_volume_grid_non_grid_aligned_volume_max() -> None:
    """volume_max=0.095 is not itself a grid point (grid: 0.03,0.05,0.07,
    0.09,0.11,...); the result must be the greatest valid grid point
    <= volume_max and <= raw."""
    result = floor_volume_to_step(Decimal("0.10"), Decimal("0.03"), Decimal("0.095"), Decimal("0.02"))
    assert result == Decimal("0.09")
    assert result <= Decimal("0.095")


def test_volume_grid_caps_down_before_flooring() -> None:
    """An enormous raw volume must never floor above volume_max - proves
    capping happens before flooring, not after."""
    result = floor_volume_to_step(Decimal("1000000"), Decimal("0.03"), Decimal("0.095"), Decimal("0.02"))
    assert result == Decimal("0.09")
    assert result <= Decimal("0.095")


def test_volume_grid_invalid_constraints_return_none() -> None:
    assert floor_volume_to_step(Decimal("1"), Decimal("0"), Decimal("10"), Decimal("0.01")) is None
    assert floor_volume_to_step(Decimal("1"), Decimal("0.01"), Decimal("10"), Decimal("0")) is None
    assert floor_volume_to_step(Decimal("1"), Decimal("10"), Decimal("1"), Decimal("0.01")) is None


# --- compute_broker_sizing: reference price rule ---


def _long_request(**overrides: object) -> MT5BrokerSizingRequest:
    fields: dict[str, object] = {
        "symbol": "EURUSD",
        "direction": TradeDirection.LONG,
        "stop_loss": Decimal("99"),
        "session_allocated_risk": Decimal("1000"),
    }
    fields.update(overrides)
    return MT5BrokerSizingRequest(**fields)


def test_explicit_entry_price_used_verbatim_long() -> None:
    facts = default_symbol_facts(bid=Decimal("50"), ask=Decimal("50.5"))  # deliberately far from entry_price
    request = _long_request(entry_price=Decimal("100"), stop_loss=Decimal("99"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE
    # price_distance = 100 - 99 = 1, not 50.5 - 99 (which would be negative/invalid)


def test_explicit_entry_price_used_verbatim_short() -> None:
    facts = default_symbol_facts(bid=Decimal("50"), ask=Decimal("50.5"))
    request = MT5BrokerSizingRequest(
        symbol="EURUSD", direction=TradeDirection.SHORT, stop_loss=Decimal("101"), entry_price=Decimal("100"), session_allocated_risk=Decimal("1000")
    )
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE


def test_long_falls_back_to_ask_when_no_entry_price() -> None:
    facts = default_symbol_facts(bid=Decimal("99.5"), ask=Decimal("100"))
    request = _long_request(stop_loss=Decimal("99"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE
    # reference=ask=100, distance=1 -> risk_per_volume_unit = (1/0.00001)*1 = 100000
    expected_volume = floor_volume_to_step(Decimal("1000") / Decimal("100000"), facts.volume_min, facts.volume_max, facts.volume_step)
    assert result.broker_volume == expected_volume


def test_short_falls_back_to_bid_when_no_entry_price() -> None:
    facts = default_symbol_facts(bid=Decimal("100"), ask=Decimal("100.5"))
    request = MT5BrokerSizingRequest(symbol="EURUSD", direction=TradeDirection.SHORT, stop_loss=Decimal("101"), session_allocated_risk=Decimal("1000"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE


def test_invalid_current_price_when_no_entry_and_bad_quote() -> None:
    facts = default_symbol_facts(ask=Decimal("0"))
    request = _long_request()
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.INVALID_CURRENT_PRICE


# --- Stop distance ---


def test_invalid_stop_distance_long_stop_above_reference() -> None:
    request = _long_request(entry_price=Decimal("100"), stop_loss=Decimal("101"))
    facts = default_symbol_facts()
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.INVALID_STOP_DISTANCE


def test_invalid_stop_distance_short_stop_below_reference() -> None:
    request = MT5BrokerSizingRequest(symbol="EURUSD", direction=TradeDirection.SHORT, entry_price=Decimal("100"), stop_loss=Decimal("99"), session_allocated_risk=Decimal("1000"))
    facts = default_symbol_facts()
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.INVALID_STOP_DISTANCE


def test_invalid_stop_distance_when_equal_to_reference() -> None:
    request = _long_request(entry_price=Decimal("100"), stop_loss=Decimal("100"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=default_symbol_facts())
    assert result.outcome is MT5SizingOutcome.INVALID_STOP_DISTANCE


# --- Trade mode restrictions ---


@pytest.mark.parametrize(
    ("direction", "trade_mode", "expected_blocked"),
    [
        (TradeDirection.LONG, MT5SymbolTradeMode.FULL, False),
        (TradeDirection.LONG, MT5SymbolTradeMode.LONG_ONLY, False),
        (TradeDirection.LONG, MT5SymbolTradeMode.SHORT_ONLY, True),
        (TradeDirection.LONG, MT5SymbolTradeMode.DISABLED, True),
        (TradeDirection.LONG, MT5SymbolTradeMode.CLOSE_ONLY, True),
        (TradeDirection.LONG, MT5SymbolTradeMode.UNKNOWN, True),
        (TradeDirection.SHORT, MT5SymbolTradeMode.FULL, False),
        (TradeDirection.SHORT, MT5SymbolTradeMode.SHORT_ONLY, False),
        (TradeDirection.SHORT, MT5SymbolTradeMode.LONG_ONLY, True),
        (TradeDirection.SHORT, MT5SymbolTradeMode.DISABLED, True),
        (TradeDirection.SHORT, MT5SymbolTradeMode.CLOSE_ONLY, True),
        (TradeDirection.SHORT, MT5SymbolTradeMode.UNKNOWN, True),
    ],
)
def test_trade_mode_direction_restrictions(direction: TradeDirection, trade_mode: MT5SymbolTradeMode, expected_blocked: bool) -> None:
    facts = default_symbol_facts(trade_mode=trade_mode)
    stop_loss = Decimal("99") if direction is TradeDirection.LONG else Decimal("101")
    request = MT5BrokerSizingRequest(symbol="EURUSD", direction=direction, entry_price=Decimal("100"), stop_loss=stop_loss, session_allocated_risk=Decimal("1000"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    if expected_blocked:
        assert result.outcome is MT5SizingOutcome.SYMBOL_NOT_TRADABLE
    else:
        assert result.outcome is MT5SizingOutcome.ACTIONABLE


# --- Tick economics / volume constraints ---


def test_invalid_tick_economics() -> None:
    facts = default_symbol_facts(trade_tick_size=Decimal("0"))
    request = _long_request(entry_price=Decimal("100"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.INVALID_TICK_ECONOMICS


def test_invalid_volume_constraints() -> None:
    facts = default_symbol_facts(volume_max=Decimal("0.001"), volume_min=Decimal("0.01"))
    request = _long_request(entry_price=Decimal("100"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.INVALID_VOLUME_CONSTRAINTS


def test_below_broker_minimum_volume() -> None:
    facts = default_symbol_facts(volume_min=Decimal("1000"), volume_max=Decimal("2000"), volume_step=Decimal("1"))
    request = _long_request(entry_price=Decimal("100"), session_allocated_risk=Decimal("0.01"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.BELOW_BROKER_MINIMUM_VOLUME


# --- Actual risk re-verification ---


def test_actual_risk_never_exceeds_allocation() -> None:
    facts = default_symbol_facts()
    request = _long_request(entry_price=Decimal("100"), stop_loss=Decimal("99"), session_allocated_risk=Decimal("1000"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE
    assert result.actual_monetary_risk is not None
    assert result.actual_monetary_risk <= Decimal("1000")


def test_above_maximum_caps_down_and_reduces_risk() -> None:
    facts = default_symbol_facts(volume_min=Decimal("0.01"), volume_max=Decimal("0.5"), volume_step=Decimal("0.01"))
    # tiny stop distance -> huge raw volume, well above volume_max
    request = _long_request(entry_price=Decimal("100.00001"), stop_loss=Decimal("100"), session_allocated_risk=Decimal("1000000"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE
    assert result.broker_volume is not None
    assert result.broker_volume <= Decimal("0.5")
    assert result.actual_monetary_risk is not None
    assert result.actual_monetary_risk <= Decimal("1000000")


def test_never_uses_stage7_recommended_units_field() -> None:
    """MT5BrokerSizingRequest structurally has no recommended_units-shaped
    field - session_allocated_risk is the sole authoritative ceiling."""
    assert "recommended_units" not in MT5BrokerSizingRequest.model_fields


def test_decimal_exactness_no_float_artifacts() -> None:
    facts = default_symbol_facts(trade_tick_size=Decimal("0.01"), trade_tick_value_loss=Decimal("0.1"))
    request = _long_request(entry_price=Decimal("100.00"), stop_loss=Decimal("99.90"), session_allocated_risk=Decimal("100"))
    result = compute_broker_sizing(as_of=NOW, request=request, symbol_facts=facts)
    assert result.outcome is MT5SizingOutcome.ACTIONABLE
    assert isinstance(result.broker_volume, Decimal)
    assert isinstance(result.actual_monetary_risk, Decimal)
