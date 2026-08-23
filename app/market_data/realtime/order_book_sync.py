"""Local order-book synchronization.

Implements Binance's documented USD-M Futures depth-stream recovery
algorithm as an explicit state machine:

    UNSYNCED -> BUFFERING -> SYNCED -> RESYNC_REQUIRED -> BUFFERING -> ...

Never applies a delta blindly: every applied delta (other than the one
event that bridges a fresh REST snapshot) is preceded by a continuity
check - its ``previous_final_update_id`` must equal the last applied
event's ``final_update_id``. Any mismatch discards the local book and
forces a full resync from a fresh snapshot; the caller is expected to
subscribe to the depth stream *before* fetching that snapshot and to keep
buffering deltas while the fetch is in flight (see
``BinanceFuturesOrderBookStream`` for the concrete wiring).

Futures-only continuity check in this stage. A future Spot strategy (Spot's
depth stream has no ``pu`` field and instead requires
``U == previous event's u + 1``) can be added later by parameterizing the
continuity predicate without touching this class's buffering/state-machine
logic - the hook is not built now because Stage 1C is Futures-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.core.enums.instrument import ContractType
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookLevel, OrderBookSnapshot

logger = logging.getLogger(__name__)


class SyncState(StrEnum):
    """Internal book-synchronization state.

    Distinct from ``StreamStatus`` (connection lifecycle): a connection can
    be CONNECTED while the book is still BUFFERING or awaiting a resync.
    """

    UNSYNCED = "UNSYNCED"
    BUFFERING = "BUFFERING"
    SYNCED = "SYNCED"
    RESYNC_REQUIRED = "RESYNC_REQUIRED"


class OrderBookSynchronizationError(Exception):
    """No valid synchronization point could be established.

    Raised when the buffered deltas don't bridge the REST snapshot's
    ``last_update_id`` at all (buffering started too late, the buffer was
    exhausted, or a gap was found while draining the buffer). The caller
    must fetch a fresh snapshot and retry - this exception never leaves the
    local book state ``SYNCED``.
    """


@dataclass(slots=True)
class _Book:
    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    asks: dict[Decimal, Decimal] = field(default_factory=dict)
    last_update_id: int = 0
    as_of: datetime = field(default_factory=lambda: datetime.fromtimestamp(0, tz=UTC))


class OrderBookSynchronizer:
    """Maintains one symbol's local order book from a REST snapshot + deltas."""

    def __init__(
        self,
        *,
        symbol: str,
        contract_type: ContractType = ContractType.PERPETUAL,
        source: str,
        max_buffer: int = 2000,
    ) -> None:
        self._symbol = symbol
        self._contract_type = contract_type
        self._source = source
        self._max_buffer = max_buffer
        self._state = SyncState.UNSYNCED
        self._buffer: list[OrderBookDeltaEvent] = []
        self._book = _Book()

    @property
    def state(self) -> SyncState:
        return self._state

    def start_buffering(self) -> None:
        """Call once the depth-stream subscription is (re)confirmed active,
        before fetching the REST snapshot."""
        self._state = SyncState.BUFFERING
        self._buffer.clear()

    def on_delta(self, delta: OrderBookDeltaEvent) -> OrderBookSnapshot | None:
        """Feed one incoming delta.

        Returns a freshly materialized ``OrderBookSnapshot`` when the book
        changed and is (still) ``SYNCED``; ``None`` while buffering, or after
        a gap forced ``RESYNC_REQUIRED`` (the caller should check
        :attr:`state` and, if ``RESYNC_REQUIRED``, restart via
        :meth:`start_buffering` + a fresh snapshot through
        :meth:`apply_snapshot`).
        """
        if self._state == SyncState.BUFFERING:
            self._buffer_delta(delta)
            return None
        if self._state != SyncState.SYNCED:
            return None

        if delta.previous_final_update_id != self._book.last_update_id:
            logger.warning(
                "order book gap for %s: expected pu=%s, got pu=%s",
                self._symbol,
                self._book.last_update_id,
                delta.previous_final_update_id,
            )
            self._state = SyncState.RESYNC_REQUIRED
            self._book = _Book()
            return None

        self._apply(delta)
        return self._materialize()

    def apply_snapshot(self, snapshot: OrderBookSnapshot) -> OrderBookSnapshot:
        """Establish (or re-establish) the book from a REST snapshot plus the
        deltas buffered since :meth:`start_buffering`.

        Raises:
            OrderBookSynchronizationError: no buffered event bridges the
                snapshot, or a gap is found while draining the buffer.
        """
        usable = [event for event in self._buffer if event.final_update_id >= snapshot.last_update_id]
        self._buffer.clear()

        sync_index = next(
            (
                index
                for index, event in enumerate(usable)
                if event.first_update_id <= snapshot.last_update_id <= event.final_update_id
            ),
            None,
        )
        if sync_index is None:
            self._state = SyncState.UNSYNCED
            raise OrderBookSynchronizationError(
                f"no buffered depth event bridges snapshot last_update_id="
                f"{snapshot.last_update_id} for {self._symbol}; fetch a fresh snapshot and retry"
            )

        self._book = _Book(
            bids={level.price: level.quantity for level in snapshot.bids},
            asks={level.price: level.quantity for level in snapshot.asks},
            last_update_id=snapshot.last_update_id,
            as_of=snapshot.timestamp,
        )
        self._state = SyncState.SYNCED

        # The sync-point event itself is exempt from the pu continuity check:
        # it bridges the REST snapshot, which is not itself a stream event
        # with a comparable "u". Continuity is enforced from the second
        # applied event onward.
        for position, event in enumerate(usable[sync_index:]):
            if position > 0 and event.previous_final_update_id != self._book.last_update_id:
                self._state = SyncState.RESYNC_REQUIRED
                raise OrderBookSynchronizationError(
                    f"gap detected for {self._symbol} while draining buffered events "
                    f"after snapshot; fetch a fresh snapshot and retry"
                )
            self._apply(event)

        return self._materialize()

    def _buffer_delta(self, delta: OrderBookDeltaEvent) -> None:
        if len(self._buffer) >= self._max_buffer:
            logger.warning(
                "order book buffer for %s exceeded %d events while waiting for snapshot; dropping oldest",
                self._symbol,
                self._max_buffer,
            )
            self._buffer.pop(0)
        self._buffer.append(delta)

    def _apply(self, delta: OrderBookDeltaEvent) -> None:
        for level in delta.bid_updates:
            self._apply_level(self._book.bids, level)
        for level in delta.ask_updates:
            self._apply_level(self._book.asks, level)
        self._book.last_update_id = delta.final_update_id
        self._book.as_of = delta.event_time

    @staticmethod
    def _apply_level(side: dict[Decimal, Decimal], level: OrderBookLevel) -> None:
        if level.quantity == 0:
            side.pop(level.price, None)
        else:
            side[level.price] = level.quantity

    def _materialize(self) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            symbol=self._symbol,
            contract_type=self._contract_type,
            last_update_id=self._book.last_update_id,
            bids=[
                OrderBookLevel(price=price, quantity=quantity)
                for price, quantity in sorted(self._book.bids.items(), reverse=True)
            ],
            asks=[
                OrderBookLevel(price=price, quantity=quantity)
                for price, quantity in sorted(self._book.asks.items())
            ],
            source=self._source,
            timestamp=self._book.as_of,
        )


__all__ = ["OrderBookSynchronizationError", "OrderBookSynchronizer", "SyncState"]
