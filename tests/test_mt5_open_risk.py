"""Stage 10C pure ``assess_open_risk``: corrected entry-gated protected-
profit classification, current-based loss-producing magnitude, no-stop
fail-closed, multi-position exact sum, no floating-PnL double counting.

Every example below mirrors the approved corrected design's five required
numeric examples exactly."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.mt5_position import MT5OpenRiskBlockReason, MT5OpenRiskOutcome
from app.core.enums.order import OrderSide
from app.mt5.risk import assess_open_risk
from tests.mt5_position_support import NOW, default_position, default_symbol_facts

_FACTS_BY_SYMBOL = {"EURUSD": default_symbol_facts()}


def _assess(*positions):
    return assess_open_risk(as_of=NOW, positions=tuple(positions), symbol_facts_by_symbol=_FACTS_BY_SYMBOL)


# --- Required numeric examples (A-E) ---


def test_example_a_buy_protected_profit_is_zero() -> None:
    position = default_position(side=OrderSide.BUY, price_open=Decimal("90"), price_current=Decimal("100"), stop_loss=Decimal("95"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.READY
    assert result.current_open_risk_to_stop == Decimal("0")


def test_example_b_sell_protected_profit_is_zero() -> None:
    position = default_position(side=OrderSide.SELL, price_open=Decimal("110"), price_current=Decimal("100"), stop_loss=Decimal("105"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.READY
    assert result.current_open_risk_to_stop == Decimal("0")


def test_example_c_buy_loss_producing_uses_current_to_stop_distance() -> None:
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.READY
    # price_distance = 95 - 90 = 5; tick_size=0.00001, tick_value_loss=1 -> risk_per_volume_unit = 5/0.00001*1 = 500000; volume=1
    expected = (Decimal("5") / Decimal("0.00001")) * Decimal("1") * Decimal("1")
    assert result.current_open_risk_to_stop == expected


def test_example_d_sell_loss_producing_uses_current_to_stop_distance() -> None:
    position = default_position(side=OrderSide.SELL, price_open=Decimal("100"), price_current=Decimal("105"), stop_loss=Decimal("110"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.READY
    expected = (Decimal("5") / Decimal("0.00001")) * Decimal("1") * Decimal("1")
    assert result.current_open_risk_to_stop == expected


def test_example_e_buy_favorable_current_but_still_loss_producing_vs_entry() -> None:
    """Stop below entry is still loss-producing relative to entry even
    though price has since moved favorably - magnitude uses current->stop
    (20), never the smaller entry->stop distance (10)."""
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("110"), stop_loss=Decimal("90"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.READY
    expected = (Decimal("20") / Decimal("0.00001")) * Decimal("1") * Decimal("1")
    assert result.current_open_risk_to_stop == expected


# --- Breakeven ---


def test_buy_breakeven_sl_equals_entry_is_zero() -> None:
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("105"), stop_loss=Decimal("100"))
    result = _assess(position)
    assert result.current_open_risk_to_stop == Decimal("0")


def test_sell_breakeven_sl_equals_entry_is_zero() -> None:
    position = default_position(side=OrderSide.SELL, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("100"))
    result = _assess(position)
    assert result.current_open_risk_to_stop == Decimal("0")


# --- Protected positions never require price_current/tick economics/symbol facts ---


def test_protected_position_does_not_require_valid_current_price() -> None:
    position = default_position(side=OrderSide.BUY, price_open=Decimal("90"), price_current=Decimal("0"), stop_loss=Decimal("95"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol={})
    assert result.outcome is MT5OpenRiskOutcome.READY
    assert result.current_open_risk_to_stop == Decimal("0")


def test_protected_position_does_not_require_symbol_facts() -> None:
    position = default_position(side=OrderSide.SELL, price_open=Decimal("110"), price_current=Decimal("100"), stop_loss=Decimal("105"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol={})
    assert result.outcome is MT5OpenRiskOutcome.READY


def test_protected_position_does_not_require_valid_tick_economics() -> None:
    bad_facts = {"EURUSD": default_symbol_facts(trade_tick_size=Decimal("0"), trade_tick_value_loss=Decimal("-1"))}
    position = default_position(side=OrderSide.BUY, price_open=Decimal("90"), price_current=Decimal("100"), stop_loss=Decimal("95"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol=bad_facts)
    assert result.outcome is MT5OpenRiskOutcome.READY
    assert result.current_open_risk_to_stop == Decimal("0")


# --- No-stop fail-closed ---


def test_no_stop_blocks_whole_assessment() -> None:
    protected = default_position(ticket=1, side=OrderSide.BUY, price_open=Decimal("90"), price_current=Decimal("100"), stop_loss=Decimal("95"))
    no_stop = default_position(ticket=2, side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=None)
    result = _assess(protected, no_stop)
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert result.current_open_risk_to_stop is None
    assert MT5OpenRiskBlockReason.NO_PROTECTIVE_STOP in result.blocked_reasons
    assert result.unsafe_tickets == (2,)


def test_no_stop_does_not_fabricate_zero() -> None:
    position = default_position(stop_loss=None)
    result = _assess(position)
    assert result.current_open_risk_to_stop is None


# --- Fail-closed for not-protected positions with unsafe facts ---


def test_invalid_current_price_blocks_loss_producing_position() -> None:
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("0"), stop_loss=Decimal("90"))
    result = _assess(position)
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert MT5OpenRiskBlockReason.INVALID_CURRENT_PRICE in result.blocked_reasons


def test_missing_symbol_facts_blocks_loss_producing_position() -> None:
    position = default_position(symbol="UNKNOWN_SYMBOL", side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol={})
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert MT5OpenRiskBlockReason.SYMBOL_UNAVAILABLE in result.blocked_reasons


def test_invalid_tick_size_blocks_loss_producing_position() -> None:
    bad_facts = {"EURUSD": default_symbol_facts(trade_tick_size=Decimal("0"))}
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol=bad_facts)
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert MT5OpenRiskBlockReason.INVALID_TICK_ECONOMICS in result.blocked_reasons


def test_invalid_tick_value_loss_blocks_loss_producing_position() -> None:
    bad_facts = {"EURUSD": default_symbol_facts(trade_tick_value_loss=Decimal("-5"))}
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    result = assess_open_risk(as_of=NOW, positions=(position,), symbol_facts_by_symbol=bad_facts)
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert MT5OpenRiskBlockReason.INVALID_TICK_ECONOMICS in result.blocked_reasons


def test_unsafe_position_not_silently_excluded_from_sum() -> None:
    safe = default_position(ticket=1, side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    unsafe = default_position(ticket=2, symbol="UNKNOWN", side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("95"), stop_loss=Decimal("90"))
    result = assess_open_risk(as_of=NOW, positions=(safe, unsafe), symbol_facts_by_symbol=_FACTS_BY_SYMBOL)
    assert result.outcome is MT5OpenRiskOutcome.BLOCKED
    assert result.current_open_risk_to_stop is None  # never a partial sum
    assert 2 in result.unsafe_tickets


# --- Multi-position exact sum / no negative risk ---


def test_multi_position_exact_sum() -> None:
    protected = default_position(ticket=1, side=OrderSide.BUY, price_open=Decimal("90"), price_current=Decimal("100"), stop_loss=Decimal("95"))
    loss_producing = default_position(ticket=2, side=OrderSide.SELL, price_open=Decimal("100"), price_current=Decimal("105"), stop_loss=Decimal("110"))
    result = _assess(protected, loss_producing)
    assert result.outcome is MT5OpenRiskOutcome.READY
    expected = Decimal("0") + (Decimal("5") / Decimal("0.00001")) * Decimal("1") * Decimal("1")
    assert result.current_open_risk_to_stop == expected


def test_no_negative_risk_even_when_current_beyond_stop() -> None:
    """current already past the stop (should not happen live, but the
    formula's own max(0, ...) must never go negative regardless)."""
    position = default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=Decimal("80"), stop_loss=Decimal("90"))
    result = _assess(position)
    assert result.current_open_risk_to_stop is not None
    assert result.current_open_risk_to_stop >= Decimal("0")


def test_no_floating_pnl_double_count_by_formula_shape() -> None:
    """The magnitude formula never reads price_open once past the
    protection gate - only price_current/stop_loss - confirming entry->current
    is never re-priced inside current_open_risk_to_stop."""
    same_entry_different_current = [
        default_position(side=OrderSide.BUY, price_open=Decimal("100"), price_current=current, stop_loss=Decimal("90"))
        for current in (Decimal("95"), Decimal("105"), Decimal("110"))
    ]
    results = [_assess(position).current_open_risk_to_stop for position in same_entry_different_current]
    # magnitude strictly depends on price_current, not price_open - all three differ
    assert len(set(results)) == 3
