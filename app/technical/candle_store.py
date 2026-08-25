"""Chronologically deterministic bounded candle retention (Stage 3A).

Unlike ``app.market_data.realtime.buffers.BoundedBuffer``'s drop-oldest-by-
insertion-order eviction (correct for Stage 1/2's continuously arriving
real-time streams, and left completely untouched here), Stage 3A candle
ingestion may legitimately arrive out of order (REST backfills, replays,
multiple sources) and retention must be deterministic BY CANDLE TIMESTAMP
regardless of arrival order:

- a late-arriving OLD candle must never evict a chronologically newer one;
- a late-arriving NEW candle must always evict the chronologically oldest
  retained candle first.

Equivalently: after inserting a full set of uniquely-timestamped candles in
any order, the retained set is always exactly the ``capacity`` candles with
the newest timestamps - this is the standard streaming top-K-by-min-eviction
result and does not depend on insertion order. ``dropped_count`` therefore
also only ever depends on the final set size versus capacity, never on the
order candles arrived in.
"""

from __future__ import annotations

from app.core.models.candle import OHLCVCandle
from app.technical.errors import DuplicateCandleTimestampError


class ChronologicalCandleStore:
    """Bounded per-key candle retention, deterministic by candle timestamp."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._by_timestamp: dict = {}
        self._dropped_count = 0

    @property
    def maxlen(self) -> int:
        return self._capacity

    @property
    def dropped_count(self) -> int:
        """Number of candles evicted so far because capacity was exceeded.

        Never incremented for a rejected duplicate (nothing was mutated) or
        for sorting/reordering (there is no separate reorder step - storage
        is always keyed by timestamp).
        """
        return self._dropped_count

    def __len__(self) -> int:
        return len(self._by_timestamp)

    def append(self, candle: OHLCVCandle) -> None:
        """Insert one candle, evicting the oldest-by-timestamp on overflow.

        Raises ``DuplicateCandleTimestampError`` if a candle with the same
        timestamp is already retained. The duplicate check happens before
        any mutation, so a rejected insert leaves existing retained history
        completely untouched - no partial corruption.
        """
        if candle.timestamp in self._by_timestamp:
            raise DuplicateCandleTimestampError(
                f"duplicate candle timestamp {candle.timestamp.isoformat()}"
            )
        self._by_timestamp[candle.timestamp] = candle
        if len(self._by_timestamp) > self._capacity:
            oldest_timestamp = min(self._by_timestamp)
            del self._by_timestamp[oldest_timestamp]
            self._dropped_count += 1

    def latest(self, count: int | None = None) -> list[OHLCVCandle]:
        """Return retained candles sorted ascending by timestamp (oldest first).

        ``count`` limits the result to the chronologically most recent
        ``count`` candles, mirroring ``BoundedBuffer.latest``'s signature.
        """
        ordered = sorted(self._by_timestamp.values(), key=lambda c: c.timestamp)
        if count is None:
            return ordered
        return ordered[-count:]


__all__ = ["ChronologicalCandleStore"]
