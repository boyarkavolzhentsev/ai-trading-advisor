"""Setup Construction price-basis reconciliation (corrective design closure,
"PROVIDER SYMBOL SPLIT + PRICE-BASIS RECONCILIATION").

Proves, with a genuinely diverging Binance reference price (never a no-op
reference == entry trick, unlike most fixtures elsewhere in this suite):

- LONG/SHORT distance translation onto the MT5 price axis
- direction-safe tick normalization
- the broker-minimum-stop-distance guard
- the basis-divergence guard
- risk_per_unit is computed exclusively from the two MT5-axis values
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.core.enums.trade import TradeDirection
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import (
    AS_OF,
    SYMBOL,
    breakout_policy_result,
    result_for,
    swing,
    symbol_facts,
    trend_following_policy_result,
    usable_market_structure,
)

_GENEROUS_DIVERGENCE_PERCENT = Decimal("100")


def _construct(
    policy_result,
    *,
    market_structure,
    facts,
    binance_reference_price,
    max_price_basis_divergence_percent=_GENEROUS_DIVERGENCE_PERCENT,
):
    return SetupConstruction().construct(
        strategy_policy_result=policy_result,
        as_of=AS_OF,
        symbol_facts=facts,
        m15_market_structure=market_structure,
        broker_symbol=SYMBOL,
        binance_reference_price=binance_reference_price,
        max_price_basis_divergence_percent=max_price_basis_divergence_percent,
    )


# --- E/F: exact LONG/SHORT translation formulas (task's own worked example) -


def test_long_translation_uses_binance_distance_never_raw_structural_price() -> None:
    """binance_reference_price=100, binance_structural_stop=95, mt5_ask=110
    -> distance=5, mt5_stop_loss=105. Never 95 (the raw Binance level)."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("1"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("110")
    assert result.setup.stop_loss == Decimal("105")
    assert result.setup.stop_loss != Decimal("95")


def test_short_translation_uses_binance_distance_never_raw_structural_price() -> None:
    """binance_reference_price=100, binance_structural_stop=105, mt5_bid=90
    -> distance=5, mt5_stop_loss=95. Never 105 (the raw Binance level)."""
    policy = breakout_policy_result(break_direction="DOWNWARD_BREAK")
    from tests.setup_construction_support import structural_break
    from app.core.enums.technical import BreakDirection

    broken = swing(kind=SwingKind.HIGH, price=Decimal("105"))
    br = structural_break(broken_swing=broken, break_close=Decimal("104"), direction=BreakDirection.DOWNWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("90.5"), bid=Decimal("90"), trade_tick_size=Decimal("1"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.BREAKOUT,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("90")
    assert result.setup.stop_loss == Decimal("95")
    assert result.setup.stop_loss != Decimal("105")


# --- invalid distance: wrong side / zero distance on the Binance axis ------


def test_zero_binance_distance_blocks_invalid_stop_side() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("100")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)


def test_negative_binance_distance_blocks_invalid_stop_side() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    # structural stop ABOVE the Binance reference - wrong side for a LONG.
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("105")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)


# --- G: direction-safe tick normalization -----------------------------------


def test_long_stop_rounds_down_away_from_entry_on_tick_boundary() -> None:
    """distance=5.003 on a tick_size=0.01 grid -> raw translated stop is
    104.997 (not tick-aligned) - LONG must round DOWN (further from entry,
    to 104.99), never up (which would narrow the realized risk distance)."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("94.997")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("0.01"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("104.99")
    actual_distance = result.setup.entry_price - result.setup.stop_loss
    assert actual_distance >= Decimal("5.003")  # rounding never narrows realized risk


def test_short_stop_rounds_up_away_from_entry_on_tick_boundary() -> None:
    """distance=5.003 on a tick_size=0.01 grid -> raw translated stop is
    95.003 (not tick-aligned) - SHORT must round UP (further from entry, to
    95.01), never down."""
    policy = breakout_policy_result(break_direction="DOWNWARD_BREAK")
    from tests.setup_construction_support import structural_break
    from app.core.enums.technical import BreakDirection

    broken = swing(kind=SwingKind.HIGH, price=Decimal("105.003"))
    br = structural_break(broken_swing=broken, break_close=Decimal("104"), direction=BreakDirection.DOWNWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("90.5"), bid=Decimal("90"), trade_tick_size=Decimal("0.01"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.BREAKOUT,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("95.01")
    actual_distance = result.setup.stop_loss - result.setup.entry_price
    assert actual_distance >= Decimal("5.003")  # rounding never narrows realized risk


# --- K: risk_per_unit is computed exclusively from the MT5-axis pair --------


def test_risk_per_unit_never_uses_raw_binance_distance() -> None:
    """entry=110, translated+rounded stop=105 (tick_size=1) ->
    risk_per_unit must equal |110-105|/tick_size*tick_value_loss = 5 * 2 =
    10 - the raw Binance distance (100-95=5) happens to numerically coincide
    here (by construction of this fixture) only because reference(100) !=
    entry(110); the point under test is that the FORMULA consumes only
    entry_price/stop_loss, both already MT5-axis values."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("1"), trade_tick_value_loss=Decimal("2"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("110")
    assert result.setup.stop_loss == Decimal("105")
    expected = abs(result.setup.entry_price - result.setup.stop_loss) / Decimal("1") * Decimal("2")
    assert result.setup.risk_per_unit == expected == Decimal("10")


def test_risk_per_unit_unaffected_by_bid_ask_spread_changes_that_do_affect_broker_validation() -> None:
    """Broker-stop validation (bid/ask-based) and risk_per_unit (entry/stop-
    based) are two genuinely different concepts (corrective review, "MT5
    BROKER STOP-LEVEL SEMANTICS") - proven here by widening the spread
    (moving bid further from ask) while holding entry_price/stop_loss fixed:
    risk_per_unit must stay byte-for-byte identical, even though the wider
    spread pushes the broker_stop_distance calculation on a genuinely
    different, unrelated code path."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))

    narrow_spread_facts = symbol_facts(
        ask=Decimal("110"), bid=Decimal("109.9"), trade_tick_size=Decimal("1"), point=Decimal("1"), trade_stops_level=0
    )
    wide_spread_facts = symbol_facts(
        ask=Decimal("110"), bid=Decimal("108"), trade_tick_size=Decimal("1"), point=Decimal("1"), trade_stops_level=0
    )

    narrow = result_for(
        _construct(policy, market_structure=ms, facts=narrow_spread_facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )
    wide = result_for(
        _construct(policy, market_structure=ms, facts=wide_spread_facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert narrow.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert wide.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert narrow.setup.entry_price == wide.setup.entry_price == Decimal("110")
    assert narrow.setup.stop_loss == wide.setup.stop_loss == Decimal("105")
    # entry/stop identical across both -> risk_per_unit identical, regardless
    # of the very different bid values (109.9 vs 108) each carries:
    assert narrow.setup.risk_per_unit == wide.setup.risk_per_unit == Decimal("5")


# --- H/I: broker minimum stop-distance enforcement (corrective review,
# "MT5 BROKER STOP-LEVEL SEMANTICS") - measured from the CURRENT opposite-
# side market quote (bid for LONG, ask for SHORT), using trade_stops_level *
# point - never entry_price, never trade_tick_size. -------------------------


def test_translated_stop_beyond_broker_minimum_allowed() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # entry=ask=110, stop=105 (ref=100, structural=95) -> broker distance =
    # bid(109.5) - stop(105) = 4.5; minimum = 3 * point(1) = 3 < 4.5 -> allowed.
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("1"), point=Decimal("1"), trade_stops_level=3)

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED


def test_translated_stop_exactly_at_broker_minimum_allowed() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # broker distance = bid(109.5) - stop(105) = 4.5; minimum = 9 * point(0.5)
    # = 4.5 -> exactly equal, allowed (strictly-less-than check).
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("1"), point=Decimal("0.5"), trade_stops_level=9)

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED


def test_translated_stop_inside_broker_minimum_blocked() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # broker distance = bid(109.5) - stop(105) = 4.5; minimum = 10 * point(0.5)
    # = 5.0 > 4.5 -> blocked.
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"), trade_tick_size=Decimal("1"), point=Decimal("0.5"), trade_stops_level=10)

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.BROKER_STOP_DISTANCE,)
    assert result.setup is None  # the structural idea is rejected, never mutated/widened


# --- G(mandatory): spread-sensitive regression - entry-based validation is
# wrong; only the opposite-side current quote is correct ---------------------


def test_long_spread_sensitive_broker_distance_blocks_where_entry_based_would_wrongly_pass() -> None:
    """LONG: ask=110, bid=109, stop=105, point=1, trade_stops_level=5.
    Entry-based (WRONG) distance = 110-105 = 5 -> would incorrectly ALLOW
    (5 is not < 5). Correct broker distance = bid(109)-stop(105) = 4 < 5 ->
    must BLOCK. A no-op Binance reference (== entry) isolates the MT5-side
    arithmetic under test."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("105")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109"), trade_tick_size=Decimal("1"), point=Decimal("1"), trade_stops_level=5)

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("110")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.BROKER_STOP_DISTANCE,)
    assert result.setup is None  # rejected outright, never mutated/widened


def test_short_spread_sensitive_broker_distance_blocks_where_entry_based_would_wrongly_pass() -> None:
    """SHORT mirror: bid=110, ask=111, stop=115, point=1, trade_stops_level=5.
    Entry-based (WRONG) distance = 115-110 = 5 -> would incorrectly ALLOW.
    Correct broker distance = stop(115)-ask(111) = 4 < 5 -> must BLOCK."""
    policy = breakout_policy_result(break_direction="DOWNWARD_BREAK")
    from tests.setup_construction_support import structural_break
    from app.core.enums.technical import BreakDirection

    broken = swing(kind=SwingKind.HIGH, price=Decimal("115"))
    br = structural_break(broken_swing=broken, break_close=Decimal("114"), direction=BreakDirection.DOWNWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("111"), bid=Decimal("110"), trade_tick_size=Decimal("1"), point=Decimal("1"), trade_stops_level=5)

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("110")),
        StrategyFamily.BREAKOUT,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.BROKER_STOP_DISTANCE,)


# --- H(mandatory): point != trade_tick_size regression ----------------------


def test_broker_minimum_uses_point_never_trade_tick_size() -> None:
    """point=0.01, trade_tick_size=0.10, trade_stops_level=10. Correct
    minimum = 10*0.01 = 0.10. The old, incorrect formula (trade_stops_level
    * trade_tick_size) would have given 10*0.10 = 1.00. The fixture's real
    broker distance (0.50) sits strictly between the two: ALLOWED under the
    correct point-based minimum, but would have been WRONGLY BLOCKED under
    the old tick-size-based one - proving the implementation uses point,
    never trade_tick_size, for this conversion."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("100.00")),))
    facts = symbol_facts(
        ask=Decimal("100.60"),
        bid=Decimal("100.50"),
        trade_tick_size=Decimal("0.10"),
        point=Decimal("0.01"),
        trade_stops_level=10,
    )

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("100.60")),
        StrategyFamily.TREND_FOLLOWING,
    )

    # broker distance = bid(100.50) - stop(100.00) = 0.50
    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("100.00")


# --- J: basis-divergence guard ----------------------------------------------


def test_basis_gap_below_threshold_allowed() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # entry=104, reference=100 -> gap = 4/100*100 = 4% < 5% threshold.
    facts = symbol_facts(ask=Decimal("104"), bid=Decimal("103.5"), trade_tick_size=Decimal("1"))

    result = result_for(
        _construct(
            policy,
            market_structure=ms,
            facts=facts,
            binance_reference_price=Decimal("100"),
            max_price_basis_divergence_percent=Decimal("5"),
        ),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED


def test_basis_gap_exactly_at_threshold_allowed() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # entry=105, reference=100 -> gap = 5/100*100 = 5% == 5% threshold -> allowed (strictly-greater-than check).
    facts = symbol_facts(ask=Decimal("105"), bid=Decimal("104.5"), trade_tick_size=Decimal("1"))

    result = result_for(
        _construct(
            policy,
            market_structure=ms,
            facts=facts,
            binance_reference_price=Decimal("100"),
            max_price_basis_divergence_percent=Decimal("5"),
        ),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED


def test_basis_gap_above_threshold_blocked() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    # entry=106, reference=100 -> gap = 6% > 5% threshold -> blocked.
    facts = symbol_facts(ask=Decimal("106"), bid=Decimal("105.5"), trade_tick_size=Decimal("1"))

    result = result_for(
        _construct(
            policy,
            market_structure=ms,
            facts=facts,
            binance_reference_price=Decimal("100"),
            max_price_basis_divergence_percent=Decimal("5"),
        ),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.PRICE_BASIS_DIVERGENCE,)
    assert result.setup is None


def test_non_positive_binance_reference_price_blocks_shared_fact_unavailable() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(
        _construct(policy, market_structure=ms, facts=facts, binance_reference_price=Decimal("0")),
        StrategyFamily.TREND_FOLLOWING,
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)
