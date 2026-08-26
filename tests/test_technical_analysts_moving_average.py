"""Tests for ``app.technical_analysts.moving_average.MovingAverageAnalyst``."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import (
    MovingAverageSlopeDirection,
    MultiPeriodMAOrdering,
    PricePositionRelativeToMA,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
)
from app.technical_analysts.moving_average import MovingAverageAnalyst
from tests.technical_analysts_support import make_moving_average, make_snapshot, status


def _observations(result, dimension):
    return [o for o in result.observations if o.dimension is dimension]


def test_price_above_sma() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("1")}, ma_slope={20: Decimal("0")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION)
    assert observation.value == PricePositionRelativeToMA.ABOVE_SMA.value
    assert observation.subject == "20"


def test_price_below_sma() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("-1")}, ma_slope={20: Decimal("0")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION)
    assert observation.value == PricePositionRelativeToMA.BELOW_SMA.value


def test_price_at_sma() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("0")}, ma_slope={20: Decimal("0")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION)
    assert observation.value == PricePositionRelativeToMA.AT_SMA.value


def test_positive_ma_slope() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("0")}, ma_slope={20: Decimal("0.5")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MA_SLOPE_DIRECTION)
    assert observation.value == MovingAverageSlopeDirection.UPWARD.value


def test_negative_ma_slope() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("0")}, ma_slope={20: Decimal("-0.5")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MA_SLOPE_DIRECTION)
    assert observation.value == MovingAverageSlopeDirection.DOWNWARD.value


def test_zero_ma_slope() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), distance_from_sma_pct={20: Decimal("0")}, ma_slope={20: Decimal("0")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MA_SLOPE_DIRECTION)
    assert observation.value == MovingAverageSlopeDirection.FLAT.value


def test_two_period_ordering_faster_above_slower() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20, 50), sma={20: Decimal("110"), 50: Decimal("100")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING)
    assert observation.value == MultiPeriodMAOrdering.FASTER_ABOVE_SLOWER.value
    assert observation.subject == "20_vs_50"


def test_two_period_ordering_faster_below_slower() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20, 50), sma={20: Decimal("90"), 50: Decimal("100")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING)
    assert observation.value == MultiPeriodMAOrdering.FASTER_BELOW_SLOWER.value


def test_two_period_ordering_equal() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20, 50), sma={20: Decimal("100"), 50: Decimal("100")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING)
    assert observation.value == MultiPeriodMAOrdering.EQUAL.value


def test_single_period_does_not_fabricate_ordering() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20,), sma={20: Decimal("100")}, distance_from_sma_pct={20: Decimal("0")}, ma_slope={20: Decimal("0")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING not in dims


def test_missing_period_values_are_skipped_not_fabricated() -> None:
    snapshot = make_snapshot(
        moving_average=make_moving_average(
            periods=(20, 50), sma={20: Decimal("110")}, distance_from_sma_pct={20: Decimal("1")}, ma_slope={20: Decimal("1")}
        )
    )
    result = MovingAverageAnalyst().analyze(snapshot)
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING not in dims
    price_observations = _observations(result, TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION)
    assert len(price_observations) == 1
    assert price_observations[0].subject == "20"


def test_deterministic_period_ordering_uses_min_max_not_declaration_order() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(50, 20), sma={20: Decimal("110"), 50: Decimal("100")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    (observation,) = _observations(result, TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING)
    assert observation.subject == "20_vs_50"
    assert observation.value == MultiPeriodMAOrdering.FASTER_ABOVE_SLOWER.value


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = MovingAverageAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = MovingAverageAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(
        moving_average=make_moving_average(
            sma={}, ema={}, distance_from_sma_pct={}, ma_slope={}, block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0)
        )
    )
    result = MovingAverageAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.observations == ()


def test_no_crossover_or_trading_vocabulary() -> None:
    snapshot = make_snapshot(moving_average=make_moving_average(periods=(20, 50), sma={20: Decimal("110"), 50: Decimal("100")}))
    result = MovingAverageAnalyst().analyze(snapshot)
    forbidden = ("CROSS", "GOLDEN", "DEATH", "BUY", "SELL", "BULLISH", "BEARISH")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()
