"""Binance USD-M futures real-time provider wiring.

Connects the generic ``WebSocketTransport`` + ``EventRouter`` to the
Binance-specific mappers and exposes the narrow
``app.market_data.realtime.protocols`` implementations. No aggregation or
book synchronization is built into these classes beyond simple per-symbol
fan-out and delegating to ``OrderBookSynchronizer`` - the classes stay
narrow, one capability each, matching how the REST
``BinanceFuturesMarketDataProvider`` is wiring-only.

Known scope limit: each capability supports one active consumer per symbol
at a time (a second concurrent call to e.g. ``trades("BTCUSDT")`` shares the
same underlying queue as the first, which is not meaningfully useful). This
is a deliberate, documented simplification for Stage 1C - a future Flow
Supervisor is expected to hold exactly one reader per symbol/capability.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable

from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookSnapshot
from app.core.models.stream_health import StreamHealth
from app.core.models.trade_event import TradeEvent
from app.market_data.exceptions import MarketDataError
from app.market_data.realtime.health import ConnectionHealthTracker
from app.market_data.realtime.order_book_sync import (
    OrderBookSynchronizationError,
    OrderBookSynchronizer,
    SyncState,
)
from app.market_data.realtime.reconnect import ReconnectPolicy
from app.market_data.realtime.router import EventRouter
from app.market_data.realtime.transport import WebSocketTransport
from app.market_data.providers.binance.futures.provider import BinanceFuturesMarketDataProvider
from app.market_data.providers.binance.futures.realtime import mapper as rt_mapper
from app.market_data.providers.binance.futures.realtime.constants import (
    ALL_MARKET_LIQUIDATION_STREAM,
    PROVIDER_NAME,
    agg_trade_stream_name,
    depth_stream_name,
    liquidation_stream_name,
    mark_price_stream_name,
)
from app.market_data.providers.binance.futures.realtime.funding_cache import FundingIntervalCache

logger = logging.getLogger(__name__)

SnapshotFetcher = Callable[[str], Awaitable[OrderBookSnapshot]]


def make_snapshot_fetcher(rest_provider: BinanceFuturesMarketDataProvider) -> SnapshotFetcher:
    """Wrap the existing (synchronous) REST order-book snapshot call for
    async use, via a worker thread - the REST layer is reused unchanged."""

    async def fetch(symbol: str) -> OrderBookSnapshot:
        return await asyncio.to_thread(rest_provider.get_order_book_snapshot, symbol)

    return fetch


def _drop_oldest_put(queue: "asyncio.Queue[object]", item: object) -> None:
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


class BinanceFuturesMarketStream:
    """Owns the shared ``/market`` connection: aggTrade + markPrice + forceOrder.

    A single physical connection carries all three capabilities (Binance's
    own stream grouping), fanned out here into per-capability, per-symbol
    bounded queues so each protocol implementation stays a thin view over
    the same underlying transport rather than opening its own connection.
    """

    def __init__(
        self,
        transport: WebSocketTransport,
        *,
        funding_interval_cache: FundingIntervalCache | None = None,
        queue_maxsize: int = 500,
    ) -> None:
        self._transport = transport
        self._funding_interval_cache = funding_interval_cache
        self._queue_maxsize = queue_maxsize
        self._router = EventRouter()
        self._router.register_pattern(
            lambda name: name.endswith("@aggTrade"),
            lambda payload: rt_mapper.map_agg_trade(payload, source=f"{PROVIDER_NAME}:agg_trade"),
        )
        self._router.register_pattern(lambda name: "@markPrice" in name, self._map_mark_price)
        self._router.register_pattern(
            lambda name: name.endswith("@forceOrder") or name == ALL_MARKET_LIQUIDATION_STREAM,
            lambda payload: rt_mapper.map_liquidation(payload, source=f"{PROVIDER_NAME}:liquidation"),
        )
        self._trade_queues: dict[str, asyncio.Queue[TradeEvent]] = {}
        self._mark_price_queues: dict[str, asyncio.Queue[FundingRate]] = {}
        self._liquidation_queue: asyncio.Queue[LiquidationEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._health = ConnectionHealthTracker(
            transport,
            provider=PROVIDER_NAME,
            stream="market",
            judge_by_silence=True,
            max_silence_seconds=30.0,
        )
        self._dispatch_task: asyncio.Task[None] | None = None

    def _map_mark_price(self, payload: object) -> FundingRate:
        symbol = payload.get("s") if isinstance(payload, dict) else None
        interval = (
            self._funding_interval_cache.get(symbol)
            if self._funding_interval_cache is not None and isinstance(symbol, str)
            else None
        )
        return rt_mapper.map_mark_price(
            payload, funding_interval_hours=interval, source=f"{PROVIDER_NAME}:mark_price"
        )

    def start(self) -> None:
        """Begin dispatching routed events into the fan-out queues (idempotent).

        Does not itself run the transport - the caller schedules
        ``transport.run()`` separately, keeping connection lifecycle and
        event fan-out as two independently testable concerns.
        """
        if self._dispatch_task is None:
            self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None

    async def _dispatch_loop(self) -> None:
        async for raw in self._transport.messages():
            event = self._router.route(raw)
            if isinstance(event, TradeEvent):
                queue = self._trade_queues.get(event.symbol)
                if queue is not None:
                    _drop_oldest_put(queue, event)
            elif isinstance(event, FundingRate):
                queue = self._mark_price_queues.get(event.symbol)
                if queue is not None:
                    _drop_oldest_put(queue, event)
            elif isinstance(event, LiquidationEvent):
                _drop_oldest_put(self._liquidation_queue, event)

    async def trades(self, symbol: str) -> AsyncIterator[TradeEvent]:
        symbol = symbol.upper()
        queue = self._trade_queues.setdefault(symbol, asyncio.Queue(maxsize=self._queue_maxsize))
        await self._transport.subscribe([agg_trade_stream_name(symbol)])
        while True:
            yield await queue.get()

    async def mark_price(self, symbol: str) -> AsyncIterator[FundingRate]:
        symbol = symbol.upper()
        queue = self._mark_price_queues.setdefault(symbol, asyncio.Queue(maxsize=self._queue_maxsize))
        await self._transport.subscribe([mark_price_stream_name(symbol)])
        while True:
            yield await queue.get()

    async def liquidations(self, symbol: str | None = None) -> AsyncIterator[LiquidationEvent]:
        stream = liquidation_stream_name(symbol) if symbol else ALL_MARKET_LIQUIDATION_STREAM
        await self._transport.subscribe([stream])
        normalized_symbol = symbol.upper() if symbol else None
        while True:
            event = await self._liquidation_queue.get()
            if normalized_symbol is None or event.symbol == normalized_symbol:
                yield event

    def health(self) -> StreamHealth:
        return self._health.snapshot()


class BinanceFuturesOrderBookStream:
    """Owns the ``/public`` depth connection for one or more symbols.

    Wires the generic ``OrderBookSynchronizer`` per symbol: subscribes to
    the depth stream first, buffers deltas while a fresh REST snapshot is
    fetched, and republishes a materialized ``OrderBookSnapshot`` on every
    successfully applied update. Never applies a delta without the
    synchronizer's continuity check.
    """

    def __init__(
        self,
        transport: WebSocketTransport,
        *,
        snapshot_fetcher: SnapshotFetcher,
        source: str = f"{PROVIDER_NAME}:order_book",
        queue_maxsize: int = 200,
        max_resync_attempts: int = 3,
        retry_policy: ReconnectPolicy | None = None,
    ) -> None:
        self._transport = transport
        self._snapshot_fetcher = snapshot_fetcher
        self._source = source
        self._queue_maxsize = queue_maxsize
        self._max_resync_attempts = max_resync_attempts
        # Retried REST snapshot fetches must back off between attempts: an
        # immediate tight retry loop against Binance's weighted REST depth
        # endpoint can itself trip rate-limiting/WAF blocks (observed live).
        self._retry_policy = retry_policy or ReconnectPolicy(
            base_seconds=1.0, factor=2.0, max_seconds=10.0
        )
        self._router = EventRouter()
        self._router.register_pattern(
            lambda name: "@depth" in name,
            lambda payload: rt_mapper.map_depth_update(payload, source=self._source),
        )
        self._synchronizers: dict[str, OrderBookSynchronizer] = {}
        self._queues: dict[str, asyncio.Queue[OrderBookSnapshot]] = {}
        self._health = ConnectionHealthTracker(
            transport,
            provider=PROVIDER_NAME,
            stream="order_book",
            judge_by_silence=True,
            max_silence_seconds=10.0,
        )
        self._dispatch_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._dispatch_task is None:
            self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None

    async def _dispatch_loop(self) -> None:
        async for raw in self._transport.messages():
            event = self._router.route(raw)
            if not isinstance(event, OrderBookDeltaEvent):
                continue
            synchronizer = self._synchronizers.get(event.symbol)
            if synchronizer is None:
                continue  # not (yet) subscribed via order_book(): ignore
            snapshot = synchronizer.on_delta(event)
            if snapshot is not None:
                self._publish(event.symbol, snapshot)
            elif synchronizer.state == SyncState.RESYNC_REQUIRED:
                asyncio.create_task(self._resync(event.symbol, synchronizer))

    def _publish(self, symbol: str, snapshot: OrderBookSnapshot) -> None:
        queue = self._queues.get(symbol)
        if queue is not None:
            _drop_oldest_put(queue, snapshot)

    async def _resync(self, symbol: str, synchronizer: OrderBookSynchronizer) -> None:
        synchronizer.start_buffering()
        for attempt in range(1, self._max_resync_attempts + 1):
            try:
                snapshot = await self._snapshot_fetcher(symbol)
                published = synchronizer.apply_snapshot(snapshot)
            except (OrderBookSynchronizationError, MarketDataError) as exc:
                logger.warning("order book resync attempt %d for %s failed: %s", attempt, symbol, exc)
                if attempt < self._max_resync_attempts:
                    delay = self._retry_policy.delay_for_attempt(attempt, jitter=random.random())
                    await asyncio.sleep(delay)
                synchronizer.start_buffering()
                continue
            self._publish(symbol, published)
            return
        logger.error(
            "order book resync for %s failed after %d attempts; book stays unsynced until "
            "the next depth event triggers another attempt",
            symbol,
            self._max_resync_attempts,
        )

    async def order_book(self, symbol: str) -> AsyncIterator[OrderBookSnapshot]:
        symbol = symbol.upper()
        synchronizer = self._synchronizers.setdefault(
            symbol, OrderBookSynchronizer(symbol=symbol, source=self._source)
        )
        queue = self._queues.setdefault(symbol, asyncio.Queue(maxsize=self._queue_maxsize))
        await self._transport.subscribe([depth_stream_name(symbol)])
        asyncio.create_task(self._resync(symbol, synchronizer))
        while True:
            yield await queue.get()

    def health(self) -> StreamHealth:
        return self._health.snapshot()


__all__ = ["BinanceFuturesMarketStream", "BinanceFuturesOrderBookStream", "make_snapshot_fetcher"]
