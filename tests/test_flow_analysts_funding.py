"""Tests for app.flow_analysts.funding.FundingAnalyst."""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, BasisSign, FundingSign, FundingTrend
from app.core.enums.quality import FeatureQuality
from app.flow_analysts.funding import FundingAnalyst
from tests.flow_analysts_support import WINDOW_1M, build_snapshot, funding_rate, make_engine


def _dim(result, dimension, window=None):
    return [o for o in result.observations if o.dimension is dimension and o.window == window]


def test_funding_sign_positive() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0005"))
    snapshot = build_snapshot(engine)

    result = FundingAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert _dim(result, AnalysisDimension.FUNDING_SIGN)[0].value == FundingSign.POSITIVE.value


def test_funding_sign_negative() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=1, rate="-0.0005"))
    snapshot = build_snapshot(engine)

    result = FundingAnalyst().analyze(snapshot)

    assert _dim(result, AnalysisDimension.FUNDING_SIGN)[0].value == FundingSign.NEGATIVE.value


def test_funding_sign_zero() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0"))
    snapshot = build_snapshot(engine)

    result = FundingAnalyst().analyze(snapshot)

    obs = _dim(result, AnalysisDimension.FUNDING_SIGN)[0]
    assert obs.value == FundingSign.ZERO.value
    assert obs.quality is FeatureQuality.VALID


def test_basis_sign_mark_above_below_and_parity() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0001", mark_price="101", index_price="100"))
    snapshot = build_snapshot(engine)
    result = FundingAnalyst().analyze(snapshot)
    assert _dim(result, AnalysisDimension.BASIS_SIGN)[0].value == BasisSign.MARK_ABOVE_INDEX.value

    engine2 = make_engine(windows=(WINDOW_1M,))
    engine2.record_funding(funding_rate(seconds_ago=1, rate="0.0001", mark_price="99", index_price="100"))
    result2 = FundingAnalyst().analyze(build_snapshot(engine2))
    assert _dim(result2, AnalysisDimension.BASIS_SIGN)[0].value == BasisSign.MARK_BELOW_INDEX.value

    engine3 = make_engine(windows=(WINDOW_1M,))
    engine3.record_funding(funding_rate(seconds_ago=1, rate="0.0001", mark_price="100", index_price="100"))
    result3 = FundingAnalyst().analyze(build_snapshot(engine3))
    assert _dim(result3, AnalysisDimension.BASIS_SIGN)[0].value == BasisSign.AT_PARITY.value


def test_funding_trend_rising_and_falling() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=90, rate="0.0001"))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0003"))
    result = FundingAnalyst().analyze(build_snapshot(engine))
    assert _dim(result, AnalysisDimension.FUNDING_TREND, window="1m")[0].value == FundingTrend.RISING.value

    engine2 = make_engine(windows=(WINDOW_1M,))
    engine2.record_funding(funding_rate(seconds_ago=90, rate="0.0003"))
    engine2.record_funding(funding_rate(seconds_ago=1, rate="0.0001"))
    result2 = FundingAnalyst().analyze(build_snapshot(engine2))
    assert _dim(result2, AnalysisDimension.FUNDING_TREND, window="1m")[0].value == FundingTrend.FALLING.value


def test_funding_trend_flat() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=90, rate="0.0002"))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0002"))
    result = FundingAnalyst().analyze(build_snapshot(engine))
    assert _dim(result, AnalysisDimension.FUNDING_TREND, window="1m")[0].value == FundingTrend.FLAT.value


def test_rolling_stddev_is_evidence_only_never_an_observation() -> None:
    engine = make_engine()  # 10s + 1m
    engine.record_funding(funding_rate(seconds_ago=90, rate="0.0001"))
    engine.record_funding(funding_rate(seconds_ago=45, rate="0.0002"))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0003"))
    snapshot = build_snapshot(engine)

    result = FundingAnalyst().analyze(snapshot)

    stddev_evidence_idx = [i for i, e in enumerate(result.evidence) if e.feature_name == "funding.rolling_stddev"]
    assert stddev_evidence_idx  # at least one window had >=2 samples
    cited_refs = {ref for o in result.observations for ref in o.evidence_refs}
    assert cited_refs.isdisjoint(stddev_evidence_idx)
    assert not any(o.dimension.value.upper().find("STDDEV") >= 0 for o in result.observations)


def test_full_abstention_when_no_history() -> None:
    engine = make_engine()
    snapshot = build_snapshot(engine)
    assert snapshot.funding.status.quality is FeatureQuality.UNAVAILABLE

    result = FundingAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_stale_propagates() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=400, rate="0.0001"))  # > 5min default staleness
    snapshot = build_snapshot(engine)
    assert snapshot.funding.status.quality is FeatureQuality.STALE

    result = FundingAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_evidence_and_provenance() -> None:
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate(seconds_ago=1, rate="0.0001"))
    snapshot = build_snapshot(engine)

    result = FundingAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "funding.latest_funding_rate" in feature_names
    assert "funding.mark_index_basis_bps" in feature_names
    assert result.provenance["funding"] == snapshot.provenance["funding"]


def test_no_forbidden_vocabulary() -> None:
    forbidden = {"HIGH", "LOW", "EXTREME", "CHEAP", "EXPENSIVE"}
    assert forbidden.isdisjoint(member.value for member in FundingSign)
    assert forbidden.isdisjoint(member.value for member in FundingTrend)
    assert forbidden.isdisjoint(member.value for member in BasisSign)


def test_multi_symbol_no_leakage() -> None:
    analyst = FundingAnalyst()
    engine = make_engine(windows=(WINDOW_1M,))
    engine.record_funding(funding_rate("BTCUSDT", seconds_ago=1, rate="0.0005"))
    engine.record_funding(funding_rate("ETHUSDT", seconds_ago=1, rate="-0.0005"))

    btc = analyst.analyze(build_snapshot(engine, symbol="BTCUSDT"))
    eth = analyst.analyze(build_snapshot(engine, symbol="ETHUSDT"))

    assert _dim(btc, AnalysisDimension.FUNDING_SIGN)[0].value == FundingSign.POSITIVE.value
    assert _dim(eth, AnalysisDimension.FUNDING_SIGN)[0].value == FundingSign.NEGATIVE.value
