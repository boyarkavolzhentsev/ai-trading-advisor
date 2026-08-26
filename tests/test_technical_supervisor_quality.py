"""Stage 3C overall-quality tests."""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.technical_supervisor_support import abstained_result, analyzed_result, full_matrix


def test_full_coverage_with_degraded_quality() -> None:
    results = [
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.STALE)
        if r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.M1
        else r
        for r in full_matrix()
    ]

    result = TechnicalSupervisor().aggregate(results)

    assert result.analyzed_count == 42
    assert result.overall_quality is FeatureQuality.STALE


def test_low_coverage_with_valid_quality() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )
    results = (analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.VALID),)

    result = supervisor.aggregate(results)

    assert result.usable_cell_ratio == 0.5
    assert result.overall_quality is FeatureQuality.VALID


def test_zero_analyzed_yields_unavailable_quality() -> None:
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1,))
    results = (abstained_result(TechnicalAnalystType.TREND, Timeframe.M1),)

    result = supervisor.aggregate(results)

    assert result.overall_quality is FeatureQuality.UNAVAILABLE


def test_worst_of_analyzed_qualities_wins() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM), expected_timeframes=(Timeframe.M1,)
    )
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.VALID),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1, quality=FeatureQuality.PARTIAL),
    )

    result = supervisor.aggregate(results)

    assert result.overall_quality is FeatureQuality.PARTIAL


def test_abstained_and_missing_do_not_affect_overall_quality() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM, TechnicalAnalystType.VOLATILITY),
        expected_timeframes=(Timeframe.M1,),
    )
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.VALID),
        abstained_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1),
        # VOLATILITY/M1 missing entirely
    )

    result = supervisor.aggregate(results)

    assert result.overall_quality is FeatureQuality.VALID


def test_embedded_analyst_result_qualities_are_preserved_unchanged() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM), expected_timeframes=(Timeframe.M1,)
    )
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.STALE),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1, quality=FeatureQuality.VALID),
    )

    result = supervisor.aggregate(results)

    by_type = {r.analyst_type: r for r in result.analyst_results}
    assert by_type[TechnicalAnalystType.TREND].quality is FeatureQuality.STALE
    assert by_type[TechnicalAnalystType.MOMENTUM].quality is FeatureQuality.VALID
