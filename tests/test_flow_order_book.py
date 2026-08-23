"""Tests for app.flow.order_book.compute_order_book_features."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.order_book_features import DepthBand
from app.flow.order_book import DEFAULT_DEPTH_BANDS, compute_order_book_features

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOWS = (AnalyticsWindow(label="1m", duration=timedelta(minutes=1)),)


def _book(*, as_of: datetime, bids: list[tuple[str, str]], asks: list[tuple[str, str]]) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        last_update_id=1,
        bids=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in bids],
        asks=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in asks],
        source="test:order_book",
        timestamp=as_of,
    )


def test_default_depth_bands_match_approved_defaults() -> None:
    by_label = {band.label: band for band in DEFAULT_DEPTH_BANDS}
    assert by_label.keys() == {"top5", "top10", "top20", "10bps", "25bps", "50bps"}
    assert by_label["top5"].top_n == 5
    assert by_label["top10"].top_n == 10
    assert by_label["top20"].top_n == 20
    assert by_label["10bps"].max_distance_bps == Decimal("10")
    assert by_label["25bps"].max_distance_bps == Decimal("25")
    assert by_label["50bps"].max_distance_bps == Decimal("50")


def test_best_bid_ask_spread_mid_spread_bps() -> None:
    book = _book(as_of=NOW, bids=[("100", "1"), ("99", "1")], asks=[("101", "1"), ("102", "1")])
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    assert features.best_bid == Decimal("100")
    assert features.best_ask == Decimal("101")
    assert features.spread == Decimal("1")
    assert features.mid_price == Decimal("100.5")
    assert features.spread_bps == Decimal("1") / Decimal("100.5") * Decimal("10000")
    assert features.status.quality is FeatureQuality.VALID


def test_no_snapshot_is_unavailable() -> None:
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[],
        bands=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    assert features.status.quality is FeatureQuality.UNAVAILABLE
    assert features.best_bid is None
    assert features.mid_price is None


def test_stale_snapshot_keeps_last_known_values() -> None:
    old = _book(as_of=NOW - timedelta(seconds=30), bids=[("100", "1")], asks=[("101", "1")])
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[old],
        bands=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
        max_staleness=timedelta(seconds=10),
    )
    assert features.status.quality is FeatureQuality.STALE
    assert features.best_bid == Decimal("100")  # not blanked


def test_top_n_band_full_coverage() -> None:
    book = _book(
        as_of=NOW,
        bids=[("100", "1"), ("99", "2"), ("98", "3")],
        asks=[("101", "1"), ("102", "2"), ("103", "3")],
    )
    band = DepthBand(label="top2", top_n=2)
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["top2"]
    assert b.bid_depth == Decimal("3")  # 1 + 2
    assert b.ask_depth == Decimal("3")  # 1 + 2
    assert b.depth_imbalance == 0.0
    assert b.status.quality is FeatureQuality.VALID


def test_top_n_band_insufficient_depth_is_partial() -> None:
    book = _book(as_of=NOW, bids=[("100", "1")], asks=[("101", "1")])
    band = DepthBand(label="top5", top_n=5)
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["top5"]
    assert b.bid_depth == Decimal("1")  # reports what's there
    assert b.status.quality is FeatureQuality.PARTIAL


def test_bps_band_full_coverage_computes_imbalance() -> None:
    # mid = 100; 10bps of 100 = 0.10 -> boundary [99.90, 100.10]
    book = _book(
        as_of=NOW,
        bids=[("99.95", "2"), ("99.80", "10")],  # 99.80 is outside band, 99.95 inside
        asks=[("100.05", "1"), ("100.20", "10")],  # 100.20 outside, 100.05 inside
    )
    band = DepthBand(label="10bps", max_distance_bps=Decimal("10"))
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["10bps"]
    assert b.bid_depth == Decimal("2")
    assert b.ask_depth == Decimal("1")
    assert b.status.quality is FeatureQuality.VALID
    assert b.depth_imbalance == float((Decimal("2") - Decimal("1")) / Decimal("3"))


def test_bps_band_thin_book_is_partial_fake_precision_guard() -> None:
    # Book only reaches 99.99/100.01 (well within a requested 50bps band) ->
    # cannot confirm the full 50bps band is captured.
    book = _book(as_of=NOW, bids=[("99.99", "1")], asks=[("100.01", "1")])
    band = DepthBand(label="50bps", max_distance_bps=Decimal("50"))
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["50bps"]
    assert b.status.quality is FeatureQuality.PARTIAL
    assert b.bid_depth == Decimal("1")  # still reports the real (partial) figure


def test_empty_side_band_is_unavailable() -> None:
    book = _book(as_of=NOW, bids=[], asks=[("101", "1")])
    band = DepthBand(label="top1", top_n=1)
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["top1"]
    assert b.bid_depth is None
    assert b.ask_depth == Decimal("1")
    assert b.status.quality is FeatureQuality.UNAVAILABLE
    assert b.depth_imbalance is None


def test_depth_band_requires_exactly_one_spec() -> None:
    import pytest

    with pytest.raises(ValueError, match="exactly one"):
        DepthBand(label="bad")
    with pytest.raises(ValueError, match="exactly one"):
        DepthBand(label="bad", top_n=5, max_distance_bps=Decimal("10"))


def test_depth_band_rejects_non_positive_top_n() -> None:
    import pytest

    with pytest.raises(ValueError, match="positive"):
        DepthBand(label="bad", top_n=0)
    with pytest.raises(ValueError, match="positive"):
        DepthBand(label="bad", top_n=-5)


def test_depth_band_rejects_non_positive_max_distance_bps() -> None:
    import pytest

    with pytest.raises(ValueError, match="positive"):
        DepthBand(label="bad", max_distance_bps=Decimal("0"))
    with pytest.raises(ValueError, match="positive"):
        DepthBand(label="bad", max_distance_bps=Decimal("-10"))


def test_depth_change_over_window() -> None:
    older = _book(as_of=NOW - timedelta(minutes=2), bids=[("100", "5")], asks=[("101", "5")])
    newer = _book(as_of=NOW, bids=[("100", "8")], asks=[("101", "3")])
    band = DepthBand(label="top1", top_n=1)
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[older, newer],
        bands=[band],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    b = features.bands["top1"]
    assert b.bid_depth_change["1m"] == Decimal("3")  # 8 - 5
    assert b.ask_depth_change["1m"] == Decimal("-2")  # 3 - 5


def test_depth_change_uses_aligned_endpoints_not_current_live_book() -> None:
    # window=1m(60s); observation_time=NOW+70s -> aligned window is (NOW, NOW+60s].
    # A book snapshot after window_end (but before observation_time) is the
    # correct "current" point-in-time book, but must NOT be used as the
    # window's "end" comparison point for depth-change.
    book_start = _book(as_of=NOW - timedelta(seconds=5), bids=[("100", "5")], asks=[("101", "5")])
    book_end = _book(as_of=NOW + timedelta(seconds=50), bids=[("100", "8")], asks=[("101", "3")])
    book_live = _book(as_of=NOW + timedelta(seconds=65), bids=[("100", "999")], asks=[("101", "999")])
    band = DepthBand(label="top1", top_n=1)
    observation_time = NOW + timedelta(seconds=70)
    features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[book_start, book_end, book_live],
        bands=[band],
        windows=WINDOWS,
        observation_time=observation_time,
        source="test:order_book",
    )
    assert features.as_of == NOW + timedelta(seconds=65)  # point-in-time: true "now", unaligned
    b = features.bands["top1"]
    assert b.bid_depth == Decimal("999")  # point-in-time depth from the live book
    assert b.bid_depth_change["1m"] == Decimal("3")  # 8 - 5, aligned endpoints only
    assert b.ask_depth_change["1m"] == Decimal("-2")  # 3 - 5


def test_multiple_symbols_independent() -> None:
    btc = _book(as_of=NOW, bids=[("100", "1")], asks=[("101", "1")])
    eth = _book(as_of=NOW, bids=[("3000", "1")], asks=[("3001", "1")])
    btc_features = compute_order_book_features(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[btc],
        bands=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    eth_features = compute_order_book_features(
        symbol="ETHUSDT",
        contract_type=ContractType.PERPETUAL,
        history=[eth],
        bands=[],
        windows=WINDOWS,
        observation_time=NOW,
        source="test:order_book",
    )
    assert btc_features.best_bid == Decimal("100")
    assert eth_features.best_bid == Decimal("3000")
