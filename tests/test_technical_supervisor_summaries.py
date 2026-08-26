"""Stage 3C per-timeframe and per-analyst summary tests."""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.technical_supervisor_support import abstained_result, analyzed_result, full_matrix


def test_per_timeframe_summary_exact_buckets_and_counts() -> None:
    results = [
        r for r in full_matrix() if not (r.analyst_type is TechnicalAnalystType.MOMENTUM and r.timeframe is Timeframe.M1)
    ]
    results.append(abstained_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1))

    result = TechnicalSupervisor().aggregate(results)
    m1_summary = next(s for s in result.per_timeframe_summaries if s.timeframe is Timeframe.M1)

    assert m1_summary.abstained_analysts == (TechnicalAnalystType.MOMENTUM,)
    assert m1_summary.analyzed_count == 6
    assert m1_summary.abstained_count == 1
    assert m1_summary.missing_count == 0
    assert m1_summary.usable_ratio == 6 / 7
    assert m1_summary.quality is FeatureQuality.VALID


def test_per_timeframe_summary_missing_analyst() -> None:
    results = [
        r for r in full_matrix() if not (r.analyst_type is TechnicalAnalystType.VOLATILITY and r.timeframe is Timeframe.H4)
    ]

    result = TechnicalSupervisor().aggregate(results)
    h4_summary = next(s for s in result.per_timeframe_summaries if s.timeframe is Timeframe.H4)

    assert h4_summary.missing_analysts == (TechnicalAnalystType.VOLATILITY,)
    assert h4_summary.missing_count == 1


def test_per_timeframe_summary_canonical_ordering() -> None:
    result = TechnicalSupervisor().aggregate(full_matrix())
    assert tuple(s.timeframe for s in result.per_timeframe_summaries) == result.expected_timeframes


def test_per_analyst_summary_exact_buckets_and_counts() -> None:
    results = [
        r for r in full_matrix() if not (r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.H4)
    ]
    results.append(abstained_result(TechnicalAnalystType.TREND, Timeframe.H4))

    result = TechnicalSupervisor().aggregate(results)
    trend_summary = next(s for s in result.per_analyst_summaries if s.analyst_type is TechnicalAnalystType.TREND)

    assert trend_summary.abstained_timeframes == (Timeframe.H4,)
    assert trend_summary.analyzed_count == 5
    assert trend_summary.abstained_count == 1
    assert trend_summary.missing_count == 0
    assert trend_summary.usable_ratio == 5 / 6
    assert trend_summary.quality is FeatureQuality.VALID


def test_per_analyst_summary_missing_timeframe() -> None:
    results = [
        r
        for r in full_matrix()
        if not (r.analyst_type is TechnicalAnalystType.RANGE_STATE and r.timeframe is Timeframe.M15)
    ]

    result = TechnicalSupervisor().aggregate(results)
    rs_summary = next(s for s in result.per_analyst_summaries if s.analyst_type is TechnicalAnalystType.RANGE_STATE)

    assert rs_summary.missing_timeframes == (Timeframe.M15,)
    assert rs_summary.missing_count == 1


def test_per_analyst_summary_canonical_ordering() -> None:
    result = TechnicalSupervisor().aggregate(full_matrix())
    assert tuple(s.analyst_type for s in result.per_analyst_summaries) == result.expected_analysts


def test_per_analyst_summary_quality_worst_of_analyzed() -> None:
    results = [
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, quality=FeatureQuality.STALE)
        if r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.M1
        else r
        for r in full_matrix()
    ]

    result = TechnicalSupervisor().aggregate(results)
    trend_summary = next(s for s in result.per_analyst_summaries if s.analyst_type is TechnicalAnalystType.TREND)

    assert trend_summary.quality is FeatureQuality.STALE


def test_per_timeframe_summary_quality_worst_of_analyzed() -> None:
    results = [
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.H4, quality=FeatureQuality.PARTIAL)
        if r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.H4
        else r
        for r in full_matrix()
    ]

    result = TechnicalSupervisor().aggregate(results)
    h4_summary = next(s for s in result.per_timeframe_summaries if s.timeframe is Timeframe.H4)

    assert h4_summary.quality is FeatureQuality.PARTIAL
