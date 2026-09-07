"""Shared fixtures for Stage 0A Flow realtime bootstrap tests.

Everything here runs against a fake, in-process WebSocket connection and
fake REST-shaped objects - no real network access happens anywhere in this
module or in any test that imports it. Mirrors
``tests/test_binance_futures_realtime_provider.py``'s own ``FakeConnection``
convention exactly, extended with the fakes Stage 0A's own bootstrap needs
(a fake open-interest source, a fake order-book snapshot fetcher, a fake
funding-interval cache).

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.flow.engine import FlowFeatureEngine
from app.flow.open_interest_poller import OpenInterestPollerConfig, OpenInterestSource
from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig
from app.market_data.exceptions import MarketDataError
from app.market_data.realtime.transport import WebSocketTransport

__all__ = [
    "NOW",
    "SYMBOL",
    "FailingOpenInterestSource",
    "FakeConnection",
    "FakeFundingIntervalCache",
    "FakeOpenInterestSource",
    "boot_transport",
    "default_snapshot_fetcher",
    "make_bootstrap",
    "make_order_book_snapshot",
    "millis",
    "shutdown_transport",
    "subscribe_message",
]

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"

_CLOSE_SENTINEL = object()


class FakeConnection:
    """In-process stand-in for ``websockets``' ``ClientConnection``."""

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


def subscribe_message(method: str, stream_names, request_id: int) -> str:
    return json.dumps({"method": method, "params": list(stream_names), "id": request_id})


def millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


async def boot_transport(connection: FakeConnection) -> tuple[WebSocketTransport, asyncio.Task]:
    async def connect() -> FakeConnection:
        return connection

    transport = WebSocketTransport(connect, build_subscribe_message=subscribe_message)
    task = asyncio.create_task(transport.run())
    await asyncio.sleep(0)
    return transport, task


async def shutdown_transport(transport: WebSocketTransport, task: asyncio.Task) -> None:
    await transport.stop()
    await asyncio.wait_for(task, timeout=1)


class FakeOpenInterestSource(OpenInterestSource):
    """Always succeeds with a fixed, real ``OpenInterest`` observation."""

    def __init__(self, *, symbol: str = SYMBOL, value: Decimal = Decimal("1000"), timestamp: datetime = NOW) -> None:
        self.calls: list[str] = []
        self._symbol = symbol
        self._value = value
        self._timestamp = timestamp

    def get_open_interest(self, symbol: str) -> OpenInterest:
        self.calls.append(symbol)
        return OpenInterest(
            symbol=self._symbol,
            contract_type=ContractType.PERPETUAL,
            open_interest=self._value,
            source="fake:open_interest",
            timestamp=self._timestamp,
        )


class FailingOpenInterestSource(OpenInterestSource):
    """Always raises a declared ``MarketDataError`` subclass."""

    def __init__(self, *, exception: MarketDataError | None = None) -> None:
        self.calls: list[str] = []
        self._exception = exception or MarketDataError("simulated transient provider failure")

    def get_open_interest(self, symbol: str) -> OpenInterest:
        self.calls.append(symbol)
        raise self._exception


class FakeFundingIntervalCache:
    """Satisfies ``FundingIntervalCache``'s two-method shape without any REST call."""

    def __init__(self) -> None:
        self.refresh_calls = 0

    def get(self, symbol: str) -> int | None:
        return None

    async def refresh_if_stale(self) -> None:
        self.refresh_calls += 1


def make_order_book_snapshot(
    *, symbol: str = SYMBOL, last_update_id: int = 100, timestamp: datetime = NOW
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol=symbol,
        contract_type=ContractType.PERPETUAL,
        last_update_id=last_update_id,
        bids=[OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
        asks=[OrderBookLevel(price=Decimal("101"), quantity=Decimal("1"))],
        source="fake:order_book",
        timestamp=timestamp,
    )


async def default_snapshot_fetcher(symbol: str) -> OrderBookSnapshot:
    return make_order_book_snapshot(symbol=symbol)


def make_bootstrap(
    *,
    market_connection: FakeConnection | None = None,
    public_connection: FakeConnection | None = None,
    market_transport: WebSocketTransport | None = None,
    public_transport: WebSocketTransport | None = None,
    symbol: str = SYMBOL,
    engine: FlowFeatureEngine | None = None,
    open_interest_provider: OpenInterestSource | None = None,
    snapshot_fetcher=None,
    rest_client=None,
    funding_interval_cache=None,
    funding_cache_check_interval_seconds: float = 60.0,
    open_interest_poll_interval_seconds: float = 60.0,
) -> tuple[FlowRealtimeBootstrap, FakeConnection | None, FakeConnection | None]:
    """Construct a fully fake-backed ``FlowRealtimeBootstrap``: real
    ``WebSocketTransport``/``BinanceFuturesMarketStream``/
    ``BinanceFuturesOrderBookStream`` classes wired to fake connections, so
    every test exercises the real integration point with zero network.

    Pass ``market_transport``/``public_transport`` directly (instead of
    ``*_connection``) when a test needs a transport with special connect
    behavior (e.g. one that always fails) - in that case the corresponding
    returned connection is ``None``.
    """
    if market_transport is None:
        market_connection = market_connection if market_connection is not None else FakeConnection()

        async def _connect_market() -> FakeConnection:
            return market_connection

        market_transport = WebSocketTransport(_connect_market, build_subscribe_message=subscribe_message)
    else:
        market_connection = None

    if public_transport is None:
        public_connection = public_connection if public_connection is not None else FakeConnection()

        async def _connect_public() -> FakeConnection:
            return public_connection

        public_transport = WebSocketTransport(_connect_public, build_subscribe_message=subscribe_message)
    else:
        public_connection = None

    config = FlowRealtimeBootstrapConfig(
        symbol=symbol,
        contract_type=ContractType.PERPETUAL,
        open_interest=OpenInterestPollerConfig(poll_interval_seconds=open_interest_poll_interval_seconds),
    )
    bootstrap = FlowRealtimeBootstrap(
        config=config,
        engine=engine if engine is not None else FlowFeatureEngine(),
        market_transport=market_transport,
        public_transport=public_transport,
        rest_client=rest_client,
        open_interest_provider=(
            open_interest_provider if open_interest_provider is not None else FakeOpenInterestSource(symbol=symbol)
        ),
        snapshot_fetcher=snapshot_fetcher if snapshot_fetcher is not None else default_snapshot_fetcher,
        funding_interval_cache=funding_interval_cache if funding_interval_cache is not None else FakeFundingIntervalCache(),
        funding_cache_check_interval_seconds=funding_cache_check_interval_seconds,
    )
    return bootstrap, market_connection, public_connection
