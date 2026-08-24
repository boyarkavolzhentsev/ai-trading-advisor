"""Tests for app.flow_analysts.order_book.OrderBookLiquidityAnalyst."""

from __future__ import annotations

from app.core.enums.flow_analysis import AgreementVerdict, AnalysisDimension, AnalystOutcome, DepthTrend, OrderBookPressure
from app.core.enums.quality import FeatureQuality
from app.core.models.order_book_features import DepthBand
from app.flow_analysts.order_book import OrderBookLiquidityAnalyst
from tests.flow_analysts_support import WINDOW_10S, build_snapshot, make_engine, order_book_snapshot


def _pressure(result, subject="top5"):
    return [o for o in result.observations if o.dimension is AnalysisDimension.DIRECTIONAL_PRESSURE and o.subject == subject]


def test_bid_heavier() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(
        order_book_snapshot(bids=[("100", "10"), ("99", "10")], asks=[("101", "1"), ("102", "1")])
    )
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert _pressure(result)[0].value == OrderBookPressure.BID_HEAVIER.value


def test_ask_heavier() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(
        order_book_snapshot(bids=[("100", "1"), ("99", "1")], asks=[("101", "10"), ("102", "10")])
    )
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert _pressure(result)[0].value == OrderBookPressure.ASK_HEAVIER.value


def test_balanced() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(
        order_book_snapshot(bids=[("100", "5"), ("99", "5")], asks=[("101", "5"), ("102", "5")])
    )
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert _pressure(result)[0].value == OrderBookPressure.BALANCED.value


def test_partial_band_when_book_thinner_than_requested_depth() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top10", top_n=10),))
    engine.record_order_book(
        order_book_snapshot(bids=[("100", "10"), ("99", "10")], asks=[("101", "1"), ("102", "1")])
    )
    snapshot = build_snapshot(engine)
    assert snapshot.order_book.bands["top10"].status.quality is FeatureQuality.PARTIAL

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    pressure = _pressure(result, subject="top10")
    assert pressure[0].quality is FeatureQuality.PARTIAL


def test_cross_band_all_agree() -> None:
    bands = (DepthBand(label="top5", top_n=5), DepthBand(label="top10", top_n=10))
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=bands)
    levels_bid = [(str(100 - i), "10") for i in range(10)]
    levels_ask = [(str(101 + i), "1") for i in range(10)]
    engine.record_order_book(order_book_snapshot(bids=levels_bid, asks=levels_ask))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    cross = [o for o in result.observations if o.dimension is AnalysisDimension.CROSS_BAND_AGREEMENT]
    assert cross[0].value == AgreementVerdict.ALL_AGREE.value


def test_cross_band_mixed() -> None:
    bands = (DepthBand(label="top2", top_n=2), DepthBand(label="top6", top_n=6))
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=bands)
    # Top 2: bid-heavy. Beyond that, ask gets much deeper -> top6 ask-heavy overall.
    bids = [("100", "10"), ("99", "10"), ("98", "1"), ("97", "1"), ("96", "1"), ("95", "1")]
    asks = [("101", "1"), ("102", "1"), ("103", "50"), ("104", "50"), ("105", "50"), ("106", "50")]
    engine.record_order_book(order_book_snapshot(bids=bids, asks=asks))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert _pressure(result, "top2")[0].value == OrderBookPressure.BID_HEAVIER.value
    assert _pressure(result, "top6")[0].value == OrderBookPressure.ASK_HEAVIER.value
    cross = [o for o in result.observations if o.dimension is AnalysisDimension.CROSS_BAND_AGREEMENT]
    assert cross[0].value == AgreementVerdict.MIXED.value


def test_cross_band_insufficient_data_with_single_band() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot(bids=[("100", "5")], asks=[("101", "5")]))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    cross = [o for o in result.observations if o.dimension is AnalysisDimension.CROSS_BAND_AGREEMENT]
    assert cross[0].value == AgreementVerdict.INSUFFICIENT_DATA.value


def test_depth_trend_thickening_thinning_unchanged() -> None:
    engine = make_engine(depth_bands=(DepthBand(label="top5", top_n=5),))  # 10s + 1m
    engine.record_order_book(order_book_snapshot(seconds_ago=90, bids=[("100", "5")], asks=[("101", "5")]))
    engine.record_order_book(order_book_snapshot(seconds_ago=1, bids=[("100", "9")], asks=[("101", "5")]))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    bid_trend = [
        o for o in result.observations if o.dimension is AnalysisDimension.DEPTH_TREND and o.subject == "top5:bid" and o.window == "1m"
    ]
    ask_trend = [
        o for o in result.observations if o.dimension is AnalysisDimension.DEPTH_TREND and o.subject == "top5:ask" and o.window == "1m"
    ]
    assert bid_trend[0].value == DepthTrend.THICKENING.value
    assert ask_trend[0].value == DepthTrend.UNCHANGED.value


def test_depth_trend_thinning() -> None:
    engine = make_engine(depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot(seconds_ago=90, bids=[("100", "9")], asks=[("101", "5")]))
    engine.record_order_book(order_book_snapshot(seconds_ago=1, bids=[("100", "3")], asks=[("101", "5")]))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    bid_trend = [
        o for o in result.observations if o.dimension is AnalysisDimension.DEPTH_TREND and o.subject == "top5:bid" and o.window == "1m"
    ]
    assert bid_trend[0].value == DepthTrend.THINNING.value


def test_spread_bps_is_evidence_only_not_an_observation() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot(bids=[("100", "5")], asks=[("101", "5")]))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    spread_idx = [i for i, e in enumerate(result.evidence) if e.feature_name == "order_book.spread_bps"]
    assert spread_idx
    cited = {ref for o in result.observations for ref in o.evidence_refs}
    assert cited.isdisjoint(spread_idx)
    assert not any("SPREAD" in o.dimension.value for o in result.observations)


def test_full_abstention_when_no_order_book_at_all() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    snapshot = build_snapshot(engine)
    assert snapshot.order_book.status.quality is FeatureQuality.UNAVAILABLE

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_stale_propagates() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot(seconds_ago=20, bids=[("100", "5")], asks=[("101", "5")]))  # >10s default staleness
    snapshot = build_snapshot(engine)
    assert snapshot.order_book.status.quality is FeatureQuality.STALE

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    pressure = _pressure(result)
    assert pressure[0].quality is FeatureQuality.STALE


def test_evidence_and_provenance() -> None:
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot(bids=[("100", "5")], asks=[("101", "5")]))
    snapshot = build_snapshot(engine)

    result = OrderBookLiquidityAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "order_book.depth_imbalance" in feature_names
    assert "order_book.best_bid" in feature_names
    assert result.provenance["order_book"] == snapshot.provenance["order_book"]
    for observation in result.observations:
        for ref in observation.evidence_refs:
            assert 0 <= ref < len(result.evidence)


def test_multi_symbol_no_leakage() -> None:
    analyst = OrderBookLiquidityAnalyst()
    engine = make_engine(windows=(WINDOW_10S,), depth_bands=(DepthBand(label="top5", top_n=5),))
    engine.record_order_book(order_book_snapshot("BTCUSDT", bids=[("100", "10")], asks=[("101", "1")]))
    engine.record_order_book(order_book_snapshot("ETHUSDT", bids=[("100", "1")], asks=[("101", "10")]))

    btc = analyst.analyze(build_snapshot(engine, symbol="BTCUSDT"))
    eth = analyst.analyze(build_snapshot(engine, symbol="ETHUSDT"))

    assert _pressure(btc)[0].value == OrderBookPressure.BID_HEAVIER.value
    assert _pressure(eth)[0].value == OrderBookPressure.ASK_HEAVIER.value
