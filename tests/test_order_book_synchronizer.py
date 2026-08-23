"""OrderBookSynchronizer: the Futures local order-book recovery algorithm.

Payload shapes follow Binance's documented "How to manage a local order book
correctly" algorithm. All values are synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookLevel, OrderBookSnapshot
from app.market_data.realtime.order_book_sync import (
    OrderBookSynchronizationError,
    OrderBookSynchronizer,
    SyncState,
)

SOURCE = "binance_futures:order_book"
NOW = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def _delta(
    *,
    first: int,
    final: int,
    prev_final: int | None,
    bids: list[tuple[str, str]] | None = None,
    asks: list[tuple[str, str]] | None = None,
    event_time: datetime = NOW,
) -> OrderBookDeltaEvent:
    return OrderBookDeltaEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        first_update_id=first,
        final_update_id=final,
        previous_final_update_id=prev_final,
        bid_updates=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in (bids or [])],
        ask_updates=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in (asks or [])],
        event_time=event_time,
        source=SOURCE,
    )


def _snapshot(
    *, last_update_id: int, bids: list[tuple[str, str]], asks: list[tuple[str, str]]
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        last_update_id=last_update_id,
        bids=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in bids],
        asks=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in asks],
        source=SOURCE,
        timestamp=NOW,
    )


def _synchronizer() -> OrderBookSynchronizer:
    return OrderBookSynchronizer(symbol="BTCUSDT", source=SOURCE)


# --------------------------------------------------------------------------- #
# state machine basics
# --------------------------------------------------------------------------- #


def test_starts_unsynced() -> None:
    assert _synchronizer().state is SyncState.UNSYNCED


def test_start_buffering_transitions_state() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    assert sync.state is SyncState.BUFFERING


def test_deltas_while_buffering_are_not_applied_and_yield_none() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    result = sync.on_delta(_delta(first=101, final=105, prev_final=100))
    assert result is None
    assert sync.state is SyncState.BUFFERING


# --------------------------------------------------------------------------- #
# initial synchronization, per Binance's documented algorithm
# --------------------------------------------------------------------------- #


def test_initial_sync_establishes_book_from_snapshot_and_buffered_deltas() -> None:
    sync = _synchronizer()
    sync.start_buffering()

    # Buffered while the REST snapshot was in flight.
    sync.on_delta(_delta(first=101, final=105, prev_final=100, bids=[("100.00", "1")]))
    sync.on_delta(_delta(first=106, final=110, prev_final=105, bids=[("100.00", "2")]))

    snapshot = _snapshot(last_update_id=105, bids=[("99.00", "5")], asks=[("101.00", "5")])
    result = sync.apply_snapshot(snapshot)

    assert sync.state is SyncState.SYNCED
    # sync point is the first buffered event whose U<=105<=u -> event(101,105);
    # event(106,110) is then applied on top.
    assert result.last_update_id == 110
    assert {level.price: level.quantity for level in result.bids} == {
        Decimal("99.00"): Decimal("5"),
        Decimal("100.00"): Decimal("2"),
    }


def test_events_entirely_before_snapshot_are_dropped() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    sync.on_delta(_delta(first=50, final=90, prev_final=49))  # final < last_update_id: must be dropped
    sync.on_delta(_delta(first=91, final=105, prev_final=90, bids=[("100.00", "1")]))

    snapshot = _snapshot(last_update_id=100, bids=[], asks=[])
    result = sync.apply_snapshot(snapshot)

    assert sync.state is SyncState.SYNCED
    assert result.last_update_id == 105


def test_no_bridging_event_raises_and_requires_fresh_snapshot() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    # Buffer starts too late: first buffered event begins after last_update_id+1.
    sync.on_delta(_delta(first=200, final=205, prev_final=199))

    snapshot = _snapshot(last_update_id=100, bids=[], asks=[])
    with pytest.raises(OrderBookSynchronizationError, match="no buffered depth event bridges"):
        sync.apply_snapshot(snapshot)
    assert sync.state is SyncState.UNSYNCED


def test_empty_buffer_raises_synchronization_error() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    snapshot = _snapshot(last_update_id=100, bids=[], asks=[])
    with pytest.raises(OrderBookSynchronizationError):
        sync.apply_snapshot(snapshot)


# --------------------------------------------------------------------------- #
# sequence continuity / gap detection while live
# --------------------------------------------------------------------------- #


def _synced() -> OrderBookSynchronizer:
    sync = _synchronizer()
    sync.start_buffering()
    sync.on_delta(_delta(first=91, final=100, prev_final=90))
    snapshot = _snapshot(last_update_id=100, bids=[("99.00", "1")], asks=[("101.00", "1")])
    sync.apply_snapshot(snapshot)
    assert sync.state is SyncState.SYNCED
    return sync


def test_continuous_deltas_apply_and_materialize() -> None:
    sync = _synced()
    result = sync.on_delta(_delta(first=101, final=102, prev_final=100, bids=[("99.00", "2")]))
    assert result is not None
    assert result.last_update_id == 102
    assert result.bids[0].quantity == Decimal("2")


def test_quantity_zero_removes_the_level() -> None:
    sync = _synced()
    result = sync.on_delta(_delta(first=101, final=102, prev_final=100, bids=[("99.00", "0")]))
    assert result is not None
    assert result.bids == []


def test_gap_in_pu_chain_triggers_resync_required_and_discards_book() -> None:
    sync = _synced()
    # prev_final should be 100 (last applied), but this event claims 105: a gap.
    result = sync.on_delta(_delta(first=106, final=110, prev_final=105))
    assert result is None
    assert sync.state is SyncState.RESYNC_REQUIRED


def test_after_gap_deltas_are_ignored_until_resynced() -> None:
    sync = _synced()
    sync.on_delta(_delta(first=106, final=110, prev_final=105))  # gap -> RESYNC_REQUIRED
    assert sync.state is SyncState.RESYNC_REQUIRED

    result = sync.on_delta(_delta(first=111, final=112, prev_final=110))
    assert result is None
    assert sync.state is SyncState.RESYNC_REQUIRED


def test_full_resynchronization_after_gap_recovers() -> None:
    sync = _synced()
    sync.on_delta(_delta(first=106, final=110, prev_final=105))  # gap
    assert sync.state is SyncState.RESYNC_REQUIRED

    # Caller restarts buffering and fetches a fresh REST snapshot.
    sync.start_buffering()
    sync.on_delta(_delta(first=201, final=205, prev_final=200, bids=[("103.00", "3")]))
    fresh_snapshot = _snapshot(last_update_id=205, bids=[("99.00", "9")], asks=[])
    result = sync.apply_snapshot(fresh_snapshot)

    assert sync.state is SyncState.SYNCED
    assert result.last_update_id == 205
    # snapshot's 99.00 plus the sync-point event's own bid update (103.00),
    # which IS applied - only its pu chain-check is skipped, not its content.
    assert {level.price for level in result.bids} == {Decimal("99.00"), Decimal("103.00")}


def test_gap_while_draining_buffered_events_after_snapshot_raises() -> None:
    sync = _synchronizer()
    sync.start_buffering()
    sync.on_delta(_delta(first=91, final=100, prev_final=90))
    # Internally inconsistent buffer: this event does not chain from 100.
    sync.on_delta(_delta(first=105, final=110, prev_final=104))

    snapshot = _snapshot(last_update_id=100, bids=[], asks=[])
    with pytest.raises(OrderBookSynchronizationError, match="gap detected"):
        sync.apply_snapshot(snapshot)
    assert sync.state is SyncState.RESYNC_REQUIRED


def test_sync_point_event_itself_is_exempt_from_pu_check() -> None:
    """The event bridging the snapshot is applied regardless of its own
    ``pu``, since the REST snapshot is not itself a stream event with a
    comparable ``u``."""
    sync = _synchronizer()
    sync.start_buffering()
    sync.on_delta(_delta(first=91, final=100, prev_final=999999))  # arbitrary/irrelevant pu
    snapshot = _snapshot(last_update_id=100, bids=[], asks=[])
    result = sync.apply_snapshot(snapshot)
    assert sync.state is SyncState.SYNCED
    assert result.last_update_id == 100


# --------------------------------------------------------------------------- #
# buffering while waiting on the REST snapshot
# --------------------------------------------------------------------------- #


def test_buffer_is_bounded_and_drops_oldest() -> None:
    sync = OrderBookSynchronizer(symbol="BTCUSDT", source=SOURCE, max_buffer=2)
    sync.start_buffering()
    sync.on_delta(_delta(first=1, final=10, prev_final=0))
    sync.on_delta(_delta(first=11, final=20, prev_final=10))
    sync.on_delta(_delta(first=21, final=30, prev_final=20))  # buffer capacity 2: oldest dropped

    # first event (1-10) was dropped, so a snapshot at last_update_id=10 can no
    # longer be bridged.
    snapshot = _snapshot(last_update_id=10, bids=[], asks=[])
    with pytest.raises(OrderBookSynchronizationError):
        sync.apply_snapshot(snapshot)
