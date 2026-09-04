"""Setup Construction TREND_FOLLOWING structural stop rule: most recent
confirmed M15 opposite-kind ``SwingPoint``, by ``candle_time`` - LOW for
LONG, HIGH for SHORT."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical import SwingKind
from app.core.enums.trade import TradeDirection
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import AS_OF, result_for, swing, symbol_facts, trend_following_policy_result, usable_market_structure


def _construct(policy_result, *, market_structure, facts=None):
    return SetupConstruction().construct(
        strategy_policy_result=policy_result,
        as_of=AS_OF,
        symbol_facts=facts if facts is not None else symbol_facts(),
        m15_market_structure=market_structure,
    )


def test_long_uses_latest_low_swing_by_candle_time() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    older = swing(kind=SwingKind.LOW, price=Decimal("95"), candle_time=AS_OF - timedelta(hours=4))
    latest = swing(kind=SwingKind.LOW, price=Decimal("98"), candle_time=AS_OF - timedelta(hours=1))
    ms = usable_market_structure(swings=(older, latest))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("98")
    assert result.setup.direction is TradeDirection.LONG
    assert result.setup.entry_price == Decimal("110")


def test_short_uses_latest_high_swing_by_candle_time() -> None:
    policy = trend_following_policy_result(direction="DOWNWARD")
    older = swing(kind=SwingKind.HIGH, price=Decimal("115"), candle_time=AS_OF - timedelta(hours=4))
    latest = swing(kind=SwingKind.HIGH, price=Decimal("112"), candle_time=AS_OF - timedelta(hours=1))
    ms = usable_market_structure(swings=(older, latest))
    facts = symbol_facts(ask=Decimal("100.5"), bid=Decimal("100"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("112")
    assert result.setup.direction is TradeDirection.SHORT
    assert result.setup.entry_price == Decimal("100")


def test_single_low_swing_selected_for_long() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("90")),))

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("90")


def test_required_swing_kind_absent_blocks_missing_stop_reference() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.HIGH, price=Decimal("120")),))  # LONG needs LOW, only HIGH present

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.MISSING_STOP_REFERENCE,)
    assert result.setup is None


def test_no_swings_at_all_blocks_missing_stop_reference() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=())

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.MISSING_STOP_REFERENCE,)


def test_wrong_side_stop_blocks_invalid_stop_side() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    # A LOW swing priced ABOVE the live ask is geometrically invalid for a LONG.
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("120")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)


def test_entry_equal_stop_is_invalid() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("110")),))  # exactly == ask

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)


def test_valid_quality_structure_succeeds() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),), quality=FeatureQuality.VALID)

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED


def test_partial_quality_structure_succeeds() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),), quality=FeatureQuality.PARTIAL)

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
