"""MT5 Price Authority Stage C: Setup Construction's structural stop is now
used directly, bit-for-bit, from the MT5-native M15 market structure - the
cross-venue price-basis translation layer (a second price axis, a distance
re-application, a basis-divergence percentage comparison) is gone entirely.

Proves, for both LONG and SHORT:
- entry_price is the live MT5 ask (LONG) / bid (SHORT) - unchanged from
  before Stage C.
- stop_loss is the MT5-native structural swing/break price, tick-normalized,
  with NO intermediate translation of any kind - never a function of
  entry_price beyond the existing tick-rounding/geometry-validation steps
  that already existed pre-Stage C.
- risk_per_unit is entry-vs-stop on the single MT5 price axis.
- the broker minimum-stop-distance guard still works, including the exact
  equality boundary (allowed, never rejected, never widened).
- invalid directional geometry still blocks.
- ``SetupBlockReason`` has no price-basis-divergence member of any kind.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.core.enums.trade import TradeDirection
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import (
    AS_OF,
    SYMBOL,
    result_for,
    swing,
    symbol_facts,
    trend_following_policy_result,
    usable_market_structure,
)


def _construct(policy_result, *, market_structure, facts):
    return SetupConstruction().construct(
        strategy_policy_result=policy_result,
        as_of=AS_OF,
        symbol_facts=facts,
        m15_market_structure=market_structure,
        broker_symbol=SYMBOL,
    )


# --------------------------------------------------------------------------- #
# A: no price-basis-divergence member exists at all
# --------------------------------------------------------------------------- #


def test_setup_block_reason_has_no_price_basis_divergence_member() -> None:
    assert not any("PRICE_BASIS" in member.name or "DIVERGENCE" in member.name for member in SetupBlockReason)
    assert {member.value for member in SetupBlockReason} == {
        "FAMILY_SETUP_UNAVAILABLE",
        "MISSING_STOP_REFERENCE",
        "INVALID_STOP_SIDE",
        "SHARED_FACT_UNAVAILABLE",
        "BROKER_STOP_DISTANCE",
    }


def test_construct_signature_carries_no_price_or_divergence_parameter() -> None:
    import inspect

    signature = inspect.signature(SetupConstruction.construct)
    for name in signature.parameters:
        assert "reference_price" not in name
        assert "divergence" not in name


# --------------------------------------------------------------------------- #
# B/C: LONG - MT5 ask entry, MT5-native stop used directly, no translation
# --------------------------------------------------------------------------- #


def test_long_entry_is_mt5_ask_and_stop_is_the_raw_swing_price_unmodified() -> None:
    """Deliberately asymmetric ask/bid so any residual translation-like
    computation involving entry_price would visibly perturb stop_loss away
    from the raw swing price - it must not."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("87.43")),))
    facts = symbol_facts(ask=Decimal("212.91"), bid=Decimal("212.50"), trade_tick_size=Decimal("0.01"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("212.91")
    assert result.setup.stop_loss == Decimal("87.43")  # the raw swing price, bit-for-bit - no translation
    assert result.setup.direction is TradeDirection.LONG


def test_long_risk_distance_is_entry_minus_stop() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.90"), trade_tick_size=Decimal("1"), trade_tick_value_loss=Decimal("1"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.risk_per_unit == (result.setup.entry_price - result.setup.stop_loss)


def test_long_tick_normalization_rounds_away_from_entry_never_widening_below_raw_distance() -> None:
    """A raw swing price that does not already sit on a tick boundary is
    rounded DOWN for LONG (away from entry, per ``ROUND_FLOOR``) - the
    realized stop distance can only grow relative to the raw swing price,
    never shrink, and never in the operator's favor."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("94.997")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.90"), trade_tick_size=Decimal("0.01"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("94.99")  # floored to the tick, never up toward entry
    assert result.setup.stop_loss <= Decimal("94.997")


# --------------------------------------------------------------------------- #
# D/E: SHORT - MT5 bid entry, MT5-native stop used directly, no translation
# --------------------------------------------------------------------------- #


def test_short_entry_is_mt5_bid_and_stop_is_the_raw_swing_price_unmodified() -> None:
    policy = trend_following_policy_result(direction="DOWNWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.HIGH, price=Decimal("305.17")),))
    facts = symbol_facts(ask=Decimal("212.91"), bid=Decimal("212.50"), trade_tick_size=Decimal("0.01"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.entry_price == Decimal("212.50")
    assert result.setup.stop_loss == Decimal("305.17")  # the raw swing price, bit-for-bit - no translation
    assert result.setup.direction is TradeDirection.SHORT


def test_short_risk_distance_is_stop_minus_entry() -> None:
    policy = trend_following_policy_result(direction="DOWNWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.HIGH, price=Decimal("125")),))
    facts = symbol_facts(ask=Decimal("110.10"), bid=Decimal("110"), trade_tick_size=Decimal("1"), trade_tick_value_loss=Decimal("1"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.risk_per_unit == (result.setup.stop_loss - result.setup.entry_price)


def test_short_tick_normalization_rounds_away_from_entry_never_widening_below_raw_distance() -> None:
    """A raw swing price above the tick boundary is rounded UP for SHORT
    (away from entry, per ``ROUND_CEILING``)."""
    policy = trend_following_policy_result(direction="DOWNWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.HIGH, price=Decimal("125.001")),))
    facts = symbol_facts(ask=Decimal("110.10"), bid=Decimal("110"), trade_tick_size=Decimal("0.01"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("125.01")  # ceilinged to the tick, never down toward entry
    assert result.setup.stop_loss >= Decimal("125.001")


# --------------------------------------------------------------------------- #
# F: invalid directional geometry still blocks
# --------------------------------------------------------------------------- #


def test_long_stop_on_wrong_side_of_entry_still_blocks_invalid_stop_side() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("115")),))  # above ask - invalid for LONG
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.90"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)
    assert result.setup is None


def test_short_stop_on_wrong_side_of_entry_still_blocks_invalid_stop_side() -> None:
    policy = trend_following_policy_result(direction="DOWNWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.HIGH, price=Decimal("100")),))  # below bid - invalid for SHORT
    facts = symbol_facts(ask=Decimal("110.10"), bid=Decimal("110"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)
    assert result.setup is None


# --------------------------------------------------------------------------- #
# G: broker minimum-stop-distance guard still works, equality still allowed
# --------------------------------------------------------------------------- #


def test_broker_stop_distance_below_minimum_still_blocks() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    # minimum = trade_stops_level(10) * point(0.01) = 0.10; bid(109.95) - stop(109.90) = 0.05 < 0.10.
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("109.90")),))
    facts = symbol_facts(
        ask=Decimal("110.00"), bid=Decimal("109.95"), trade_tick_size=Decimal("0.01"), trade_stops_level=10, point=Decimal("0.01")
    )

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.BROKER_STOP_DISTANCE,)
    assert result.setup is None


def test_broker_stop_distance_exactly_at_minimum_is_allowed_never_widened() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    # minimum = 10 * 0.01 = 0.10; bid(109.95) - stop(109.85) = 0.10 exactly.
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("109.85")),))
    facts = symbol_facts(
        ask=Decimal("110.00"), bid=Decimal("109.95"), trade_tick_size=Decimal("0.01"), trade_stops_level=10, point=Decimal("0.01")
    )

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("109.85")  # never widened to create extra margin
