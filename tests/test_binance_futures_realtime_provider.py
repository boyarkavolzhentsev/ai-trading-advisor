"""BinanceFuturesMarketStream / BinanceFuturesOrderBookStream wiring.

Everything runs against a fake, in-process WebSocket connection and a fake
REST snapshot fetcher - no real network access happens here.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.stream_health import StreamHealth
from app.market_data.exceptions import ProviderUnavailableError
from app.market_data.realtime.order_book_sync import SyncState
from app.market_data.realtime.reconnect import ReconnectPolicy
from app.market_data.realtime.transport import WebSocketTransport
from app.market_data.providers.binance.futures.realtime.provider import (
    BinanceFuturesMarketStream,
    BinanceFuturesOrderBookStream,
)

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)

_CLOSE_SENTINEL = object()


class FakeConnection:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def push(self, frame: str) -> None:
        self._queue.put_nowait(frame)

    def push_envelope(self, stream: str, data: dict) -> None:
        self.push(json.dumps({"stream": stream, "data": data}))

    def __aiter__(self):
        return self._generator()

    async def _generator(self):
        while True:
            item = await self._queue.get()
            if item is _CLOSE_SENTINEL:
                return
            yield item

    async def close(self) -> None:
        self.closed = True
        self._queue.put_nowait(_CLOSE_SENTINEL)


def _subscribe_message(method: str, stream_names, request_id: int) -> str:
    return json.dumps({"method": method, "params": list(stream_names), "id": request_id})


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


async def _boot(connection: FakeConnection) -> tuple[WebSocketTransport, asyncio.Task]:
    async def connect() -> FakeConnection:
        return connection

    transport = WebSocketTransport(connect, build_subscribe_message=_subscribe_message)
    task = asyncio.create_task(transport.run())
    await asyncio.sleep(0)
    return transport, task


async def _shutdown(transport: WebSocketTransport, task: asyncio.Task) -> None:
    await transport.stop()
    await asyncio.wait_for(task, timeout=1)


# --------------------------------------------------------------------------- #
# BinanceFuturesMarketStream: trades, mark price, liquidations
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trades_are_mapped_and_filtered_by_symbol() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    stream = BinanceFuturesMarketStream(transport)
    stream.start()

    trades = stream.trades("BTCUSDT")
    connection.push_envelope(
        "btcusdt@aggTrade",
        {
            "e": "aggTrade", "E": _millis(NOW), "s": "BTCUSDT", "a": 1,
            "p": "64000.00", "q": "0.1", "f": 1, "l": 1, "T": _millis(NOW), "m": False,
        },
    )
    trade = await asyncio.wait_for(anext(trades), timeout=1)

    assert trade.symbol == "BTCUSDT"
    assert trade.side is OrderSide.BUY
    assert trade.contract_type is ContractType.PERPETUAL

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_mark_price_uses_funding_interval_cache() -> None:
    class _FakeIntervalCache:
        def get(self, symbol: str) -> int | None:
            return 4 if symbol == "BTCUSDT" else None

    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    stream = BinanceFuturesMarketStream(transport, funding_interval_cache=_FakeIntervalCache())
    stream.start()

    updates = stream.mark_price("BTCUSDT")
    connection.push_envelope(
        "btcusdt@markPrice@1s",
        {
            "e": "markPriceUpdate", "E": _millis(NOW), "s": "BTCUSDT",
            "p": "64000.00", "i": "63999.00", "r": "0.0001", "T": _millis(NOW),
        },
    )
    funding = await asyncio.wait_for(anext(updates), timeout=1)

    assert funding.funding_interval_hours == 4
    assert funding.symbol == "BTCUSDT"

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_liquidations_scoped_to_one_symbol_ignore_others() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    stream = BinanceFuturesMarketStream(transport)
    stream.start()

    liquidations = stream.liquidations("BTCUSDT")

    def order(symbol: str) -> dict:
        return {
            "s": symbol, "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "1",
            "p": "1", "ap": "1", "X": "FILLED", "l": "1", "z": "1", "T": _millis(NOW),
        }

    connection.push_envelope("!forceOrder@arr", {"e": "forceOrder", "E": _millis(NOW), "o": order("ETHUSDT")})
    connection.push_envelope("!forceOrder@arr", {"e": "forceOrder", "E": _millis(NOW), "o": order("BTCUSDT")})

    event = await asyncio.wait_for(anext(liquidations), timeout=1)
    assert event.symbol == "BTCUSDT"

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_malformed_agg_trade_does_not_crash_the_dispatch_loop() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    stream = BinanceFuturesMarketStream(transport)
    stream.start()

    trades = stream.trades("BTCUSDT")
    connection.push_envelope("btcusdt@aggTrade", {"s": "BTCUSDT"})  # missing required fields
    connection.push_envelope(
        "btcusdt@aggTrade",
        {
            "e": "aggTrade", "E": _millis(NOW), "s": "BTCUSDT", "a": 2,
            "p": "1", "q": "1", "f": 1, "l": 1, "T": _millis(NOW), "m": True,
        },
    )
    trade = await asyncio.wait_for(anext(trades), timeout=1)
    assert trade.trade_id == 2

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_market_stream_health_reports_provider_and_stream() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    stream = BinanceFuturesMarketStream(transport)

    health = stream.health()
    assert isinstance(health, StreamHealth)
    assert health.provider == "binance_futures"
    assert health.stream == "market"

    await _shutdown(transport, transport_task)


# --------------------------------------------------------------------------- #
# BinanceFuturesOrderBookStream: synchronization + REST recovery
# --------------------------------------------------------------------------- #


def _snapshot(*, last_update_id: int) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        last_update_id=last_update_id,
        bids=[OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
        asks=[OrderBookLevel(price=Decimal("101"), quantity=Decimal("1"))],
        source="binance_futures:order_book",
        timestamp=NOW,
    )


def _depth_payload(*, first: int, final: int, prev_final: int) -> dict:
    return {
        "e": "depthUpdate", "E": _millis(NOW), "T": _millis(NOW), "s": "BTCUSDT",
        "U": first, "u": final, "pu": prev_final, "b": [], "a": [],
    }


class StepFetcher:
    """Deterministic test double for the REST snapshot fetcher.

    Each call blocks until the test explicitly releases it via
    :meth:`release`, eliminating the sleep-duration races a real (or
    simulated-delay) fetch would introduce between "push a delta" and "the
    fetch completes and consumes the buffer".
    """

    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.call_count = 0
        self._gates: list[asyncio.Event] = []

    async def __call__(self, symbol: str) -> OrderBookSnapshot:
        self.call_count += 1
        gate = asyncio.Event()
        self._gates.append(gate)
        await gate.wait()
        result = self._results[self.call_count - 1]
        if isinstance(result, BaseException):
            raise result
        return result

    async def wait_until_call(self, n: int) -> None:
        """Block until the nth call (1-based) has started and is gated."""
        async with asyncio.timeout(1):
            while len(self._gates) < n:
                await asyncio.sleep(0)

    def release(self, n: int) -> None:
        """Let the nth call (1-based) proceed to return/raise its result."""
        self._gates[n - 1].set()


async def _start_iterating(books) -> asyncio.Task:  # noqa: ANN001 - async generator, no clean type
    """Begin advancing an ``order_book()`` async generator without awaiting
    its result yet.

    An async generator's body (subscribe + spawn the first resync task) does
    not run at all until first advanced - callers must start this before
    pushing any delta they expect the resync to observe.
    """
    task = asyncio.ensure_future(anext(books))
    await asyncio.sleep(0)  # let the generator's setup and the resync task's start_buffering() run
    return task


@pytest.mark.asyncio
async def test_initial_synchronization_uses_rest_snapshot_and_buffered_deltas() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    fetcher = StepFetcher([_snapshot(last_update_id=100)])

    stream = BinanceFuturesOrderBookStream(transport, snapshot_fetcher=fetcher)
    stream.start()
    books = stream.order_book("BTCUSDT")
    pending = await _start_iterating(books)

    await fetcher.wait_until_call(1)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=91, final=100, prev_final=90))
    await asyncio.sleep(0.01)  # let the delta propagate through transport -> router -> buffer
    fetcher.release(1)

    snapshot = await asyncio.wait_for(pending, timeout=1)
    assert snapshot.last_update_id == 100

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_rest_snapshot_failure_is_retried_and_recovers() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    fetcher = StepFetcher([ProviderUnavailableError("transient network error"), _snapshot(last_update_id=100)])

    stream = BinanceFuturesOrderBookStream(
        transport,
        snapshot_fetcher=fetcher,
        max_resync_attempts=3,
        retry_policy=ReconnectPolicy(base_seconds=0.001, factor=2.0, max_seconds=0.005),
    )
    stream.start()
    books = stream.order_book("BTCUSDT")
    pending = await _start_iterating(books)

    await fetcher.wait_until_call(1)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=91, final=100, prev_final=90))
    await asyncio.sleep(0.01)
    fetcher.release(1)  # attempt 1 fails -> synchronizer restarts buffering for the retry

    await fetcher.wait_until_call(2)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=91, final=100, prev_final=90))
    await asyncio.sleep(0.01)
    fetcher.release(2)  # attempt 2 succeeds

    snapshot = await asyncio.wait_for(pending, timeout=1)
    assert snapshot.last_update_id == 100
    assert fetcher.call_count == 2

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_rest_snapshot_permanent_failure_gives_up_without_crashing_loop() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    fetcher = StepFetcher(
        [ProviderUnavailableError("venue unreachable"), ProviderUnavailableError("still unreachable")]
    )

    stream = BinanceFuturesOrderBookStream(
        transport,
        snapshot_fetcher=fetcher,
        max_resync_attempts=2,
        retry_policy=ReconnectPolicy(base_seconds=0.001, factor=2.0, max_seconds=0.005),
    )
    stream.start()
    books = stream.order_book("BTCUSDT")
    await _start_iterating(books)

    await fetcher.wait_until_call(1)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=91, final=100, prev_final=90))
    fetcher.release(1)

    await fetcher.wait_until_call(2)
    fetcher.release(2)
    await asyncio.sleep(0.01)  # let the resync coroutine finish giving up

    assert fetcher.call_count == 2
    assert stream._dispatch_task is not None  # noqa: SLF001 - proving the loop is still alive
    assert not stream._dispatch_task.done()  # noqa: SLF001
    synchronizer = stream._synchronizers["BTCUSDT"]  # noqa: SLF001
    assert synchronizer.state is not SyncState.SYNCED  # gave up: never established

    await stream.stop()
    await _shutdown(transport, transport_task)


@pytest.mark.asyncio
async def test_gap_triggers_a_fresh_resync() -> None:
    connection = FakeConnection()
    transport, transport_task = await _boot(connection)
    fetcher = StepFetcher([_snapshot(last_update_id=100), _snapshot(last_update_id=300)])

    stream = BinanceFuturesOrderBookStream(transport, snapshot_fetcher=fetcher)
    stream.start()
    books = stream.order_book("BTCUSDT")
    pending = await _start_iterating(books)

    await fetcher.wait_until_call(1)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=91, final=100, prev_final=90))
    await asyncio.sleep(0.01)
    fetcher.release(1)
    first_snapshot = await asyncio.wait_for(pending, timeout=1)
    assert first_snapshot.last_update_id == 100

    next_pending = asyncio.ensure_future(anext(books))
    await asyncio.sleep(0)

    # A gap: pu should be 100, but this claims 150. The wiring reacts by
    # kicking off a resync immediately.
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=151, final=160, prev_final=150))

    # Recovery: the resync task fetches a fresh snapshot; this bridging
    # delta is buffered while that fetch is gated.
    await fetcher.wait_until_call(2)
    connection.push_envelope("btcusdt@depth@100ms", _depth_payload(first=291, final=300, prev_final=290))
    await asyncio.sleep(0.01)
    fetcher.release(2)

    second_snapshot = await asyncio.wait_for(next_pending, timeout=1)
    assert second_snapshot.last_update_id == 300
    assert fetcher.call_count == 2

    await stream.stop()
    await _shutdown(transport, transport_task)
