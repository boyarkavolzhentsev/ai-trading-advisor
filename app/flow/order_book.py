"""Deterministic order-book / microstructure calculator.

Operates over a supplied bounded history of ``OrderBookSnapshot``s (the
latest is picked as the most recent snapshot at/before ``observation_time``,
never interpolated). Supports both top-N and basis-point-from-mid depth
bands (``app.core.models.order_book_features.DepthBand``); a band whose
requested reach exceeds what the available book actually covers is marked
``PARTIAL`` rather than silently reported as if it were complete (the
fake-precision guard). Weighted (distance-discounted) imbalance is
deliberately not implemented - only the unweighted ``depth_imbalance``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.feature_status import FeatureStatus
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.order_book_features import DepthBand, DepthBandFeatures, OrderBookFeatures
from app.flow.quality import stale, unavailable, valid, worse_of
from app.flow.windows import latest_at_or_before, window_bounds

DEFAULT_MAX_STALENESS = timedelta(seconds=10)

DEFAULT_DEPTH_BANDS: tuple[DepthBand, ...] = (
    DepthBand(label="top5", top_n=5),
    DepthBand(label="top10", top_n=10),
    DepthBand(label="top20", top_n=20),
    DepthBand(label="10bps", max_distance_bps=Decimal("10")),
    DepthBand(label="25bps", max_distance_bps=Decimal("25")),
    DepthBand(label="50bps", max_distance_bps=Decimal("50")),
)
"""Configurable defaults only - never referenced positionally by calculators."""

_BPS_DIVISOR = Decimal("10000")


def _mid_price(snapshot: OrderBookSnapshot) -> Decimal | None:
    if not snapshot.bids or not snapshot.asks:
        return None
    return (snapshot.bids[0].price + snapshot.asks[0].price) / 2


def _side_band_depth(
    levels: Sequence[OrderBookLevel], band: DepthBand, mid_price: Decimal | None
) -> tuple[Decimal | None, bool]:
    """Return ``(depth, covered)`` for one book side against one band.

    ``covered`` is ``False`` when the available levels do not reach the
    requested band boundary (or when there is no data on this side at all) -
    the caller must mark such a result ``PARTIAL``, never pretend it is
    complete.
    """
    if not levels:
        return None, False
    if band.top_n is not None:
        selected = levels[: band.top_n]
        depth = sum((level.quantity for level in selected), start=Decimal("0"))
        return depth, len(levels) >= band.top_n

    assert band.max_distance_bps is not None
    if mid_price is None or mid_price == 0:
        return None, False
    max_distance = mid_price * band.max_distance_bps / _BPS_DIVISOR
    selected = [level for level in levels if abs(level.price - mid_price) <= max_distance]
    depth = sum((level.quantity for level in selected), start=Decimal("0"))
    worst_distance = abs(levels[-1].price - mid_price)
    return depth, worst_distance >= max_distance


def _band_features(
    band: DepthBand,
    snapshot: OrderBookSnapshot,
    history: Sequence[OrderBookSnapshot],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    freshness_quality: FeatureQuality,
    freshness_reason: str | None,
) -> DepthBandFeatures:
    mid = _mid_price(snapshot)
    bid_depth, bid_covered = _side_band_depth(snapshot.bids, band, mid)
    ask_depth, ask_covered = _side_band_depth(snapshot.asks, band, mid)

    reasons: list[str] = [freshness_reason] if freshness_reason else []
    if bid_depth is None or ask_depth is None:
        quality = FeatureQuality.UNAVAILABLE
        reasons.append(f"band {band.label!r} has no data on one or both sides")
        depth_imbalance = None
    else:
        depth_sufficiency = FeatureQuality.VALID if (bid_covered and ask_covered) else FeatureQuality.PARTIAL
        if depth_sufficiency is FeatureQuality.PARTIAL:
            insufficient_sides = [
                side for side, covered in (("bid", bid_covered), ("ask", ask_covered)) if not covered
            ]
            reasons.append(
                f"band {band.label!r} exceeds available book depth on {' and '.join(insufficient_sides)} side"
            )
        quality = worse_of(freshness_quality, depth_sufficiency)
        total = bid_depth + ask_depth
        depth_imbalance = float((bid_depth - ask_depth) / total) if total > 0 else None

    # Depth-change compares the two UTC epoch-aligned window endpoints (the
    # book at/before window_end vs. at/before window_start), not "current"
    # vs. "window_start ago" - so it is exactly window.duration wide and
    # reproducible for any observation_time within the same aligned bucket.
    bid_depth_change: dict[str, Decimal] = {}
    ask_depth_change: dict[str, Decimal] = {}
    for window in windows:
        window_start, window_end = window_bounds(observation_time, window.duration)
        end_snapshot = latest_at_or_before(history, timestamp_of=lambda s: s.timestamp, cutoff=window_end)
        start_snapshot = latest_at_or_before(history, timestamp_of=lambda s: s.timestamp, cutoff=window_start)
        if end_snapshot is None or start_snapshot is None or end_snapshot is start_snapshot:
            continue
        end_bid_depth, _ = _side_band_depth(end_snapshot.bids, band, _mid_price(end_snapshot))
        end_ask_depth, _ = _side_band_depth(end_snapshot.asks, band, _mid_price(end_snapshot))
        start_bid_depth, _ = _side_band_depth(start_snapshot.bids, band, _mid_price(start_snapshot))
        start_ask_depth, _ = _side_band_depth(start_snapshot.asks, band, _mid_price(start_snapshot))
        if end_bid_depth is not None and start_bid_depth is not None:
            bid_depth_change[window.label] = end_bid_depth - start_bid_depth
        if end_ask_depth is not None and start_ask_depth is not None:
            ask_depth_change[window.label] = end_ask_depth - start_ask_depth

    sample_count = len(snapshot.bids) + len(snapshot.asks)
    return DepthBandFeatures(
        band=band,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        depth_imbalance=depth_imbalance,
        bid_depth_change=bid_depth_change,
        ask_depth_change=ask_depth_change,
        status=FeatureStatus(quality=quality, sample_count=sample_count, reasons=reasons),
    )


def compute_order_book_features(
    *,
    symbol: str,
    contract_type: ContractType,
    history: Sequence[OrderBookSnapshot],
    bands: Sequence[DepthBand],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
    max_staleness: timedelta = DEFAULT_MAX_STALENESS,
) -> OrderBookFeatures:
    """Compute point-in-time order-book microstructure features."""
    latest = latest_at_or_before(history, timestamp_of=lambda snapshot: snapshot.timestamp, cutoff=observation_time)

    if latest is None:
        return OrderBookFeatures(
            symbol=symbol,
            contract_type=contract_type,
            as_of=observation_time,
            status=unavailable("no order book snapshot available"),
            source=source,
        )

    best_bid = latest.bids[0].price if latest.bids else None
    best_ask = latest.asks[0].price if latest.asks else None
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    mid_price = _mid_price(latest)
    spread_bps = (spread / mid_price * _BPS_DIVISOR) if spread is not None and mid_price and mid_price > 0 else None

    staleness_seconds = (observation_time - latest.timestamp).total_seconds()
    is_stale = staleness_seconds > max_staleness.total_seconds()
    freshness_quality = FeatureQuality.STALE if is_stale else FeatureQuality.VALID
    freshness_reason = (
        f"order book snapshot is {staleness_seconds:.3f}s old (max {max_staleness.total_seconds()}s)"
        if is_stale
        else None
    )

    band_features = {
        band.label: _band_features(band, latest, history, windows, observation_time, freshness_quality, freshness_reason)
        for band in bands
    }

    top_status = stale(freshness_reason, sample_count=1) if is_stale else valid(1)

    return OrderBookFeatures(
        symbol=symbol,
        contract_type=contract_type,
        as_of=latest.timestamp,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_bps=spread_bps,
        mid_price=mid_price,
        bands=band_features,
        status=top_status,
        source=source,
    )


__all__ = ["DEFAULT_DEPTH_BANDS", "DEFAULT_MAX_STALENESS", "compute_order_book_features"]
