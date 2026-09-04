"""Setup Construction's shared-fact fail-closed semantics: the two facts
every structure-capable family equally depends on (MT5 symbol facts, M15
``MarketStructureFeatures``) fail closed to ``SHARED_FACT_UNAVAILABLE`` -
missing, below approved quality, or unusable tick economics - never a
timeframe fallback, never a per-family reason."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.quality import FeatureQuality
from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import AS_OF, result_for, swing, symbol_facts, trend_following_policy_result, unusable_market_structure, usable_market_structure

_USABLE_SWING = (swing(kind=SwingKind.LOW, price=Decimal("95")),)


def _construct(policy_result, *, facts, market_structure):
    return SetupConstruction().construct(
        strategy_policy_result=policy_result, as_of=AS_OF, symbol_facts=facts, m15_market_structure=market_structure
    )


def test_missing_m15_structure_blocks_shared_fact_unavailable() -> None:
    policy = trend_following_policy_result(direction="UPWARD")

    result = result_for(
        _construct(policy, facts=symbol_facts(), market_structure=None), StrategyFamily.TREND_FOLLOWING
    )

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)


@pytest.mark.parametrize("quality", [FeatureQuality.STALE, FeatureQuality.UNAVAILABLE])
def test_below_approved_quality_structure_blocks_shared_fact_unavailable(quality: FeatureQuality) -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = unusable_market_structure(quality=quality)

    result = result_for(_construct(policy, facts=symbol_facts(), market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)


def test_missing_symbol_facts_blocks_shared_fact_unavailable() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=_USABLE_SWING)

    result = result_for(_construct(policy, facts=None, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)


@pytest.mark.parametrize("tick_size", [Decimal("0"), Decimal("-0.01")])
def test_invalid_tick_size_blocks_shared_fact_unavailable(tick_size: Decimal) -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=_USABLE_SWING)
    facts = symbol_facts(trade_tick_size=tick_size)

    result = result_for(_construct(policy, facts=facts, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)


@pytest.mark.parametrize("tick_value_loss", [Decimal("0"), Decimal("-1")])
def test_invalid_tick_value_loss_blocks_shared_fact_unavailable(tick_value_loss: Decimal) -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=_USABLE_SWING)
    facts = symbol_facts(trade_tick_value_loss=tick_value_loss)

    result = result_for(_construct(policy, facts=facts, market_structure=ms), StrategyFamily.TREND_FOLLOWING)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)


def test_no_timeframe_fallback_is_ever_attempted() -> None:
    """An unusable M15 structure fails closed outright - Setup Construction
    never substitutes any other timeframe's structure, and there is no
    parameter through which it even could."""
    import inspect

    signature = inspect.signature(SetupConstruction.construct)
    assert list(signature.parameters) == ["self", "strategy_policy_result", "as_of", "symbol_facts", "m15_market_structure"]
