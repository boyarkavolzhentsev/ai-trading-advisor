"""Tests for app.technical.candle_store.ChronologicalCandleStore.

Proves retention is deterministic BY CANDLE TIMESTAMP regardless of
insertion order - the correction required after the initial Stage 3A
implementation reported an insertion-order-dependent eviction risk.
"""

from __future__ import annotations

import itertools

import pytest

from app.technical.candle_store import ChronologicalCandleStore
from app.technical.errors import DuplicateCandleTimestampError
from tests.technical_support import candle


def _candles(*indices: int):
    return [candle(index=i, close=str(100 + i)) for i in indices]


def test_capacity_retains_newest_n_by_timestamp() -> None:
    store = ChronologicalCandleStore(capacity=3)
    for c in _candles(0, 1, 2, 3, 4):
        store.append(c)
    retained = [c.timestamp for c in store.latest()]
    expected = [c.timestamp for c in _candles(2, 3, 4)]
    assert retained == expected


def test_chronological_order_insertion() -> None:
    store = ChronologicalCandleStore(capacity=3)
    for c in _candles(0, 1, 2):
        store.append(c)
    assert [c.timestamp for c in store.latest()] == [c.timestamp for c in _candles(0, 1, 2)]


def test_reverse_chronological_order_produces_same_final_history() -> None:
    forward = ChronologicalCandleStore(capacity=3)
    for c in _candles(0, 1, 2, 3, 4):
        forward.append(c)

    reverse = ChronologicalCandleStore(capacity=3)
    for c in reversed(_candles(0, 1, 2, 3, 4)):
        reverse.append(c)

    assert [c.timestamp for c in forward.latest()] == [c.timestamp for c in reverse.latest()]
    assert forward.dropped_count == reverse.dropped_count


def test_very_old_late_candle_cannot_evict_a_newer_candle() -> None:
    store = ChronologicalCandleStore(capacity=3)
    for c in _candles(5, 6, 7):  # store now holds the 3 newest so far
        store.append(c)
    before = [c.timestamp for c in store.latest()]

    very_old = candle(index=0, close="1")  # older than everything retained
    store.append(very_old)

    after = [c.timestamp for c in store.latest()]
    assert after == before  # unchanged - the old candle evicted only itself
    assert very_old.timestamp not in after
    assert store.dropped_count == 1


def test_newer_late_candle_evicts_chronologically_oldest_retained() -> None:
    store = ChronologicalCandleStore(capacity=3)
    for c in _candles(0, 1, 2):
        store.append(c)

    newer = candle(index=10, close="999")
    store.append(newer)

    retained_timestamps = [c.timestamp for c in store.latest()]
    assert _candles(0)[0].timestamp not in retained_timestamps  # oldest evicted
    assert retained_timestamps == [c.timestamp for c in _candles(1, 2, 10)]
    assert store.dropped_count == 1


@pytest.mark.parametrize("order", list(itertools.permutations(range(4))))
def test_mixed_order_batch_ingestion_is_deterministic(order: tuple[int, ...]) -> None:
    store = ChronologicalCandleStore(capacity=2)
    source = _candles(0, 1, 2, 3)
    for i in order:
        store.append(source[i])

    assert [c.timestamp for c in store.latest()] == [c.timestamp for c in _candles(2, 3)]
    assert store.dropped_count == 2  # 4 inserted, capacity 2 -> 2 evicted, regardless of order


def test_equivalent_candle_sets_different_orders_identical_retained_set() -> None:
    source = _candles(0, 1, 2, 3, 4, 5)
    orders = [
        list(range(6)),
        list(reversed(range(6))),
        [3, 1, 4, 0, 5, 2],
        [5, 4, 3, 2, 1, 0],
    ]
    results = []
    for order in orders:
        store = ChronologicalCandleStore(capacity=4)
        for i in order:
            store.append(source[i])
        results.append(tuple(c.timestamp for c in store.latest()))

    assert len(set(results)) == 1  # every order converges to the identical retained set


def test_dropped_count_increments_only_for_capacity_eviction() -> None:
    store = ChronologicalCandleStore(capacity=5)
    for c in _candles(0, 1, 2):  # well under capacity
        store.append(c)
    assert store.dropped_count == 0


def test_duplicate_timestamp_rejected() -> None:
    store = ChronologicalCandleStore(capacity=5)
    c = candle(index=0, close="100")
    store.append(c)
    with pytest.raises(DuplicateCandleTimestampError):
        store.append(candle(index=0, close="101"))


def test_failed_duplicate_ingestion_does_not_corrupt_existing_history() -> None:
    store = ChronologicalCandleStore(capacity=5)
    for c in _candles(0, 1, 2):
        store.append(c)
    before = [c.timestamp for c in store.latest()]
    dropped_before = store.dropped_count

    with pytest.raises(DuplicateCandleTimestampError):
        store.append(candle(index=1, close="999"))

    assert [c.timestamp for c in store.latest()] == before
    assert store.dropped_count == dropped_before
    assert len(store) == 3


def test_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ChronologicalCandleStore(capacity=0)
