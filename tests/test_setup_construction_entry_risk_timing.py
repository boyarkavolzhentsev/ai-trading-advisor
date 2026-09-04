"""Setup Construction entry-price policy, risk_per_unit formula, timing
policy, and multi-family independence."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.setup_construction import SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.enums.trade import TradeDirection
from app.core.config.constants import SIGNAL_EXECUTION_WINDOW
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import (
    AS_OF,
    combined_trend_following_and_breakout_policy_result,
    result_for,
    structural_break,
    swing,
    symbol_facts,
    trend_following_policy_result,
    usable_market_structure,
)


def _trend_setup(*, direction: str, ask: Decimal, bid: Decimal, stop: Decimal, kind: SwingKind):
    policy = trend_following_policy_result(direction=direction)
    ms = usable_market_structure(swings=(swing(kind=kind, price=stop),))
    facts = symbol_facts(ask=ask, bid=bid)
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms
    )
    return result_for(setup_result, StrategyFamily.TREND_FOLLOWING)


def test_long_entry_uses_ask() -> None:
    result = _trend_setup(direction="UPWARD", ask=Decimal("110.25"), bid=Decimal("110.00"), stop=Decimal("95"), kind=SwingKind.LOW)
    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("110.25")


def test_short_entry_uses_bid() -> None:
    result = _trend_setup(direction="DOWNWARD", ask=Decimal("110.25"), bid=Decimal("110.00"), stop=Decimal("120"), kind=SwingKind.HIGH)
    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("110.00")


def test_entry_price_is_bit_exact_copy_of_supplied_symbol_facts_quote() -> None:
    """Never a Technical/Binance candle price, never a re-derived value -
    the resolved entry_price is exactly the supplied MT5SymbolFacts field,
    with no rounding/transformation of any kind."""
    ask = Decimal("12345.6789012345")
    result = _trend_setup(direction="UPWARD", ask=ask, bid=Decimal("12340"), stop=Decimal("12000"), kind=SwingKind.LOW)
    assert result.setup.entry_price is ask or result.setup.entry_price == ask


def test_risk_per_unit_exact_decimal_formula() -> None:
    entry = Decimal("110")
    stop = Decimal("95")
    tick_size = Decimal("0.01")
    tick_value_loss = Decimal("2.5")
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=stop),))
    facts = symbol_facts(ask=entry, bid=entry - Decimal("0.5"), trade_tick_size=tick_size, trade_tick_value_loss=tick_value_loss)

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)

    expected = (abs(entry - stop) / tick_size) * tick_value_loss
    assert result.setup.risk_per_unit == expected


def test_risk_per_unit_uses_full_decimal_precision_no_quantization() -> None:
    entry = Decimal("1.234567")
    stop = Decimal("1.200001")
    tick_size = Decimal("0.0000001")
    tick_value_loss = Decimal("0.333333333333")
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=stop),))
    facts = symbol_facts(ask=entry, bid=entry, trade_tick_size=tick_size, trade_tick_value_loss=tick_value_loss)

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)

    expected = (abs(entry - stop) / tick_size) * tick_value_loss
    assert result.setup.risk_per_unit == expected  # bit-exact, never a rounded/quantized approximation


def test_signal_time_equals_caller_supplied_as_of() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    assert result.setup.signal_time == AS_OF


def test_valid_until_equals_as_of_plus_signal_execution_window() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    assert result.setup.valid_until == AS_OF + SIGNAL_EXECUTION_WINDOW


def test_multi_family_results_are_independent_and_preserve_policy_order() -> None:
    policy = combined_trend_following_and_breakout_policy_result()

    tf_swing = swing(kind=SwingKind.LOW, price=Decimal("95"))
    broken = swing(kind=SwingKind.HIGH, price=Decimal("100"))
    br = structural_break(broken_swing=broken, break_close=Decimal("105"), direction=BreakDirection.UPWARD_BREAK)
    ms = usable_market_structure(swings=(tf_swing,), breaks=(br,))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms
    )

    expected_families = tuple(
        r.family for r in policy.family_results if r.family in (StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT)
    )
    actual_families = tuple(r.family for r in setup_result.family_results)
    assert actual_families == expected_families  # canonical Policy order preserved, never reordered/ranked

    tf_result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    bo_result = result_for(setup_result, StrategyFamily.BREAKOUT)
    assert tf_result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert bo_result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert tf_result.setup.stop_loss == Decimal("95")  # TREND_FOLLOWING's own swing, unaffected by BREAKOUT's
    assert bo_result.setup.stop_loss == Decimal("100")  # BREAKOUT's own break, unaffected by TREND_FOLLOWING's


def test_one_family_blocked_does_not_block_the_other_when_shared_facts_are_valid() -> None:
    policy = combined_trend_following_and_breakout_policy_result()
    # No swing of the required LOW kind -> TREND_FOLLOWING blocked; BREAKOUT still has its own valid break.
    broken = swing(kind=SwingKind.HIGH, price=Decimal("100"))
    br = structural_break(broken_swing=broken, break_close=Decimal("105"), direction=BreakDirection.UPWARD_BREAK)
    ms = usable_market_structure(swings=(), breaks=(br,))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms
    )

    tf_result = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    bo_result = result_for(setup_result, StrategyFamily.BREAKOUT)
    assert tf_result.outcome is SetupConstructionOutcome.BLOCKED
    assert bo_result.outcome is SetupConstructionOutcome.CONSTRUCTED
