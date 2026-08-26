"""Cross-cutting quality/abstention semantics shared by every Stage 3B analyst.

Complements the per-analyst quality/abstention assertions already made in
each ``tests/test_technical_analysts_<domain>.py`` file with the general
principles the approved design requires of every analyst uniformly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalystOutcome
from app.technical_analysts.candle_structure import CandleStructureAnalyst
from app.technical_analysts.market_structure import MarketStructureAnalyst
from app.technical_analysts.momentum import MomentumAnalyst
from app.technical_analysts.moving_average import MovingAverageAnalyst
from app.technical_analysts.range_state import RangeStateAnalyst
from app.technical_analysts.trend import TrendAnalyst
from app.technical_analysts.volatility import VolatilityAnalyst
from tests.technical_analysts_support import (
    make_candle_structure,
    make_market_structure,
    make_momentum,
    make_moving_average,
    make_range_state,
    make_snapshot,
    make_trend,
    make_volatility,
    status,
)

ALL_ANALYSTS = (
    TrendAnalyst(),
    MarketStructureAnalyst(),
    VolatilityAnalyst(),
    MomentumAnalyst(),
    MovingAverageAnalyst(),
    CandleStructureAnalyst(),
    RangeStateAnalyst(),
)


@pytest.mark.parametrize("analyst", ALL_ANALYSTS, ids=lambda a: type(a).__name__)
def test_abstained_result_has_no_observations_and_unavailable_quality(analyst) -> None:
    unavailable = status(FeatureQuality.UNAVAILABLE, sample_count=0)
    snapshot = make_snapshot(
        trend=make_trend(return_pct=None, slope=None, directional_persistence=None, block_status=unavailable),
        market_structure=make_market_structure(block_status=unavailable),
        volatility=make_volatility(true_range=None, atr=None, rolling_range=None, range_expansion_ratio=None, block_status=unavailable),
        momentum=make_momentum(roc=None, rsi=None, block_status=unavailable),
        moving_average=make_moving_average(sma={}, ema={}, distance_from_sma_pct={}, ma_slope={}, block_status=unavailable),
        candle_structure=make_candle_structure(
            candle_time=None, body_size=None, upper_wick=None, lower_wick=None, range_size=None,
            body_to_range_ratio=None, close_location_value=None, block_status=unavailable,
        ),
        range_state=make_range_state(rolling_range=None, normalized_range=None, directional_efficiency=None, block_status=unavailable),
    )
    result = analyst.analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


@pytest.mark.parametrize("analyst", ALL_ANALYSTS, ids=lambda a: type(a).__name__)
def test_analyzed_result_never_carries_abstention_reasons(analyst) -> None:
    snapshot = make_snapshot(
        trend=make_trend(return_pct=Decimal("1")),
        volatility=make_volatility(range_expansion_ratio=Decimal("1.2")),
        momentum=make_momentum(roc=Decimal("1")),
    )
    result = analyst.analyze(snapshot)
    if result.status is TechnicalAnalystOutcome.ANALYZED:
        assert result.abstention_reasons == ()


def test_zero_return_is_valid_not_unknown() -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("0")))
    result = TrendAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    observation = next(o for o in result.observations if o.dimension.value == "RETURN_DIRECTION")
    assert observation.value == "FLAT"


def test_rsi_midpoint_is_valid_not_unknown() -> None:
    snapshot = make_snapshot(momentum=make_momentum(rsi=Decimal("50")))
    result = MomentumAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    observation = next(o for o in result.observations if o.dimension.value == "RSI_MIDPOINT_RELATION")
    assert observation.value == "AT_MIDPOINT"


def test_valid_empty_break_set_is_not_unavailable() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(), breaks=(), block_status=status(FeatureQuality.VALID, sample_count=20)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    observation = next(o for o in result.observations if o.dimension.value == "STRUCTURAL_BREAK_PRESENCE")
    assert observation.value == "NO_BREAK_CONFIRMED"


@pytest.mark.parametrize("analyst", ALL_ANALYSTS, ids=lambda a: type(a).__name__)
def test_partial_and_stale_still_analyze_with_degraded_quality(analyst) -> None:
    for quality in (FeatureQuality.PARTIAL, FeatureQuality.STALE):
        degraded = status(quality, sample_count=3)
        snapshot = make_snapshot(
            trend=make_trend(return_pct=Decimal("1"), block_status=degraded),
            market_structure=make_market_structure(block_status=degraded),
            volatility=make_volatility(range_expansion_ratio=Decimal("1.1"), block_status=degraded),
            momentum=make_momentum(roc=Decimal("1"), block_status=degraded),
            moving_average=make_moving_average(block_status=degraded),
            candle_structure=make_candle_structure(block_status=degraded),
            range_state=make_range_state(block_status=degraded),
        )
        result = analyst.analyze(snapshot)
        assert result.status is TechnicalAnalystOutcome.ANALYZED
        assert result.quality is quality
