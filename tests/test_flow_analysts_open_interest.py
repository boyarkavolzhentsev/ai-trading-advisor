"""Tests for app.flow_analysts.open_interest.OpenInterestAnalyst."""

from __future__ import annotations

from app.core.enums.flow_analysis import AgreementVerdict, AnalysisDimension, AnalystOutcome, OpenInterestTrend, OrdinalTrend
from app.core.enums.quality import FeatureQuality
from app.flow_analysts.open_interest import OpenInterestAnalyst
from tests.flow_analysts_support import WINDOW_1M, build_snapshot, make_engine, open_interest


def _trend(result, dimension=AnalysisDimension.OPEN_INTEREST_TREND, window="1m"):
    return [o for o in result.observations if o.dimension is dimension and o.window == window]


def test_expanding() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="110"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert _trend(result)[0].value == OpenInterestTrend.EXPANDING.value
    velocity = _trend(result, AnalysisDimension.OPEN_INTEREST_VELOCITY_TREND)
    assert velocity[0].value == OpenInterestTrend.EXPANDING.value


def test_contracting() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="90"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    assert _trend(result)[0].value == OpenInterestTrend.CONTRACTING.value


def test_flat() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="100"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    assert _trend(result)[0].value == OpenInterestTrend.FLAT.value


def test_full_abstention_when_no_history() -> None:
    engine = make_engine()
    snapshot = build_snapshot(engine)
    assert snapshot.open_interest.status.quality is FeatureQuality.UNAVAILABLE

    result = OpenInterestAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_stale_propagates() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=400, value="100"))  # > 5min default staleness
    snapshot = build_snapshot(engine)
    assert snapshot.open_interest.status.quality is FeatureQuality.STALE

    result = OpenInterestAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_persistence_all_agree_and_magnitude_trend_stable() -> None:
    engine = make_engine()  # 10s + 1m
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="110"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert persistence[0].value == AgreementVerdict.ALL_AGREE.value
    assert trend[0].value == OrdinalTrend.STABLE.value


def test_persistence_mixed_across_windows() -> None:
    engine = make_engine()  # 10s + 1m
    engine.record_open_interest(open_interest(seconds_ago=90, value="80"))
    engine.record_open_interest(open_interest(seconds_ago=30, value="150"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="100"))
    snapshot = build_snapshot(engine)

    # 10s window: start ref = 150 (seconds_ago=30 <= NOW-10s), end = 100 -> contracting.
    # 1m window: start ref = 80 (seconds_ago=90 <= NOW-60s), end = 100 -> expanding.
    assert snapshot.open_interest.windows["10s"].percent_change < 0
    assert snapshot.open_interest.windows["1m"].percent_change > 0

    result = OpenInterestAnalyst().analyze(snapshot)

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert persistence[0].value == AgreementVerdict.MIXED.value
    # shortest(10s) percent_change is negative, longest(1m) is positive -> shortest < longest
    assert trend[0].value == OrdinalTrend.DECREASING.value


def test_magnitude_trend_increasing() -> None:
    engine = make_engine()  # 10s + 1m
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=30, value="50"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="200"))
    snapshot = build_snapshot(engine)

    # 10s: start=50, end=200 -> +300%. 1m: start=100, end=200 -> +100%.
    assert snapshot.open_interest.windows["10s"].percent_change > snapshot.open_interest.windows["1m"].percent_change

    result = OpenInterestAnalyst().analyze(snapshot)

    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert trend[0].value == OrdinalTrend.INCREASING.value


def test_persistence_insufficient_with_single_window() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="110"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert persistence[0].value == AgreementVerdict.INSUFFICIENT_DATA.value
    assert trend[0].value == OrdinalTrend.INSUFFICIENT_DATA.value


def test_evidence_and_provenance() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="110"))
    snapshot = build_snapshot(engine)

    result = OpenInterestAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "open_interest.percent_change" in feature_names
    assert "open_interest.oi_velocity" in feature_names
    assert result.provenance["open_interest"] == snapshot.provenance["open_interest"]


def test_no_abnormal_vocabulary() -> None:
    forbidden = {"UNUSUAL", "EXTREME", "HIGH", "LOW", "STRONG", "WEAK"}
    assert forbidden.isdisjoint(member.value for member in OpenInterestTrend)


def test_multi_symbol_no_leakage() -> None:
    analyst = OpenInterestAnalyst()
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_open_interest(open_interest("BTCUSDT", seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest("BTCUSDT", seconds_ago=1, value="110"))
    engine.record_open_interest(open_interest("ETHUSDT", seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest("ETHUSDT", seconds_ago=1, value="90"))

    btc = analyst.analyze(build_snapshot(engine, symbol="BTCUSDT"))
    eth = analyst.analyze(build_snapshot(engine, symbol="ETHUSDT"))

    assert _trend(btc)[0].value == OpenInterestTrend.EXPANDING.value
    assert _trend(eth)[0].value == OpenInterestTrend.CONTRACTING.value
