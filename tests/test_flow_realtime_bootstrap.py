"""Stage 0A ``FlowRealtimeBootstrap`` lifecycle tests: start/stop, idempotency,
partial stream availability, no dangling owned tasks. No real network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.core.enums.stream import StreamStatus
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.realtime.transport import WebSocketTransport
from tests.flow_realtime_bootstrap_support import default_snapshot_fetcher, make_bootstrap, subscribe_message


def _all_tasks_done(tasks: list[asyncio.Task]) -> bool:
    return all(task.done() for task in tasks)


@pytest.mark.asyncio
async def test_start_connects_and_stop_leaves_no_dangling_tasks() -> None:
    bootstrap, _, _ = make_bootstrap()

    await bootstrap.start()
    await asyncio.sleep(0.02)

    health = bootstrap.health()
    assert health.market.status is StreamStatus.CONNECTED
    assert health.order_book.status is StreamStatus.CONNECTED

    consumer_task_names = ("trades", "liquidations", "order_book", "funding", "funding_cache_refresh")
    forward_tasks = [bootstrap._tasks[name] for name in consumer_task_names]
    market_task = bootstrap._tasks["market_transport"]
    public_task = bootstrap._tasks["public_transport"]
    oi_task = bootstrap._oi_poller._task

    await bootstrap.stop()

    assert _all_tasks_done(forward_tasks)
    assert market_task is not None and market_task.done()
    assert public_task is not None and public_task.done()
    assert oi_task is not None and oi_task.done()
    assert bootstrap._tasks == {}


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    bootstrap, _, _ = make_bootstrap()
    await bootstrap.start()
    first_market_task = bootstrap._tasks["market_transport"]
    await bootstrap.start()
    assert bootstrap._tasks["market_transport"] is first_market_task
    await bootstrap.stop()


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    bootstrap, _, _ = make_bootstrap()
    await bootstrap.start()
    await bootstrap.stop()
    # a second stop() must not raise and must not attempt to re-close an
    # already-closed/torn-down resource
    await bootstrap.stop()


@pytest.mark.asyncio
async def test_does_not_wait_for_analytical_warm_up_before_returning() -> None:
    """start() must complete promptly even though no market event has
    arrived yet - readiness is answered by build_flow_result(), never by
    start() itself blocking."""
    bootstrap, _, _ = make_bootstrap()
    await asyncio.wait_for(bootstrap.start(), timeout=1)
    await bootstrap.stop()


@pytest.mark.asyncio
async def test_partial_stream_availability_does_not_prevent_start() -> None:
    """One transport failing to connect must not prevent the other from
    working, and must not raise out of start()."""

    async def _connect_public_refuses() -> None:
        raise OSError("connection refused")

    public_transport = WebSocketTransport(_connect_public_refuses, build_subscribe_message=subscribe_message)
    bootstrap, market_connection, _ = make_bootstrap(public_transport=public_transport)

    await asyncio.wait_for(bootstrap.start(), timeout=1)
    await asyncio.sleep(0.05)

    health = bootstrap.health()
    assert health.market.status is StreamStatus.CONNECTED
    assert health.order_book.status in (StreamStatus.CONNECTING, StreamStatus.RECONNECTING, StreamStatus.DISCONNECTED)

    # Flow result must still be constructible (degraded, not blocked)
    result = bootstrap.build_flow_result(as_of=datetime.now(UTC))
    assert result is not None

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_stop_closes_only_owned_rest_client() -> None:
    """A caller-injected rest_client must never be closed by the bootstrap;
    one the bootstrap constructed itself must be closeable independently."""
    close_calls = {"count": 0}

    class TrackedRestClient(BinanceRestClient):
        def close(self) -> None:
            close_calls["count"] += 1
            super().close()

    injected_client = TrackedRestClient()
    bootstrap, _, _ = make_bootstrap(rest_client=injected_client)

    await bootstrap.start()
    await bootstrap.stop()

    assert close_calls["count"] == 0
    injected_client.close()  # caller's own responsibility, not the bootstrap's


@pytest.mark.asyncio
async def test_stop_closes_self_constructed_rest_client() -> None:
    """When no rest_client/open_interest_provider/snapshot_fetcher/
    funding_interval_cache is injected, the bootstrap constructs and must
    close its own REST client on stop()."""
    from app.core.enums.instrument import ContractType
    from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig
    from tests.flow_realtime_bootstrap_support import FakeConnection

    market_connection = FakeConnection()
    public_connection = FakeConnection()

    async def _connect_market() -> FakeConnection:
        return market_connection

    async def _connect_public() -> FakeConnection:
        return public_connection

    market_transport = WebSocketTransport(_connect_market, build_subscribe_message=subscribe_message)
    public_transport = WebSocketTransport(_connect_public, build_subscribe_message=subscribe_message)

    config = FlowRealtimeBootstrapConfig(symbol="BTCUSDT", contract_type=ContractType.PERPETUAL)
    bootstrap = FlowRealtimeBootstrap(config=config, market_transport=market_transport, public_transport=public_transport)

    assert bootstrap._owns_rest_client is True
    rest_client = bootstrap._rest_client
    assert rest_client is not None

    await bootstrap.start()
    await bootstrap.stop()
    # closing an already-closed httpx.Client a second time must not raise
    rest_client.close()
