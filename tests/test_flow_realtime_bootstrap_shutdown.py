"""Stage 0A reconnect/resync interaction and clean-shutdown tests. No real
network."""

from __future__ import annotations

import asyncio

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.stream import StreamStatus
from app.flow.engine import FlowFeatureEngine
from app.flow.open_interest_poller import TaskState
from app.market_data.providers.binance.futures.realtime.constants import depth_stream_name
from app.market_data.realtime.order_book_sync import SyncState
from app.market_data.realtime.transport import WebSocketTransport
from tests.flow_realtime_bootstrap_support import (
    NOW,
    SYMBOL,
    FakeConnection,
    make_bootstrap,
    make_order_book_snapshot,
    millis,
    subscribe_message,
)


def _millis(dt) -> int:
    return millis(dt)


def _agg_trade_envelope(trade_id: int):
    return (
        f"{SYMBOL.lower()}@aggTrade",
        {"e": "aggTrade", "E": _millis(NOW), "s": SYMBOL, "a": trade_id, "p": "64000.00", "q": "0.1", "f": trade_id, "l": trade_id, "T": _millis(NOW), "m": False},
    )


@pytest.mark.asyncio
async def test_transport_reconnect_preserves_engine_history() -> None:
    """A transport-level reconnect must never clear retained
    FlowFeatureEngine history - only the connection is transient. Simulates
    a real reconnect by having the connect() factory hand back a genuinely
    NEW connection object on each call, exactly as a real dropped socket
    would be replaced by a fresh one."""
    engine = FlowFeatureEngine()
    connections: list[FakeConnection] = []

    async def connect() -> FakeConnection:
        connection = FakeConnection()
        connections.append(connection)
        return connection

    market_transport = WebSocketTransport(connect, build_subscribe_message=subscribe_message)
    bootstrap, _, _ = make_bootstrap(engine=engine, market_transport=market_transport)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    assert len(connections) == 1

    stream, payload = _agg_trade_envelope(1)
    connections[0].push_envelope(stream, payload)
    await asyncio.sleep(0.05)
    assert len(engine.history_for(SYMBOL, ContractType.PERPETUAL).trades.latest()) == 1

    # Simulate a dropped connection: the transport's run() loop must
    # reconnect on its own via connect() (a fresh FakeConnection), and the
    # already-retained history must remain exactly as it was.
    await connections[0].close()
    await asyncio.sleep(0.05)
    assert len(connections) >= 2, "transport did not reconnect with a new connection"

    retained_after_drop = engine.history_for(SYMBOL, ContractType.PERPETUAL).trades.latest()
    assert len(retained_after_drop) == 1  # untouched by the disconnect

    stream, payload = _agg_trade_envelope(2)
    connections[-1].push_envelope(stream, payload)
    await asyncio.sleep(0.05)

    retained_after_reconnect = engine.history_for(SYMBOL, ContractType.PERPETUAL).trades.latest()
    assert len(retained_after_reconnect) == 2  # prior trade preserved, new one added post-reconnect

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_order_book_resync_never_emits_fabricated_intermediate_snapshot() -> None:
    """While BUFFERING (subscribed, no bridging snapshot applied yet), no
    OrderBookSnapshot may be recorded into the engine - only a successfully
    applied/materialized book, never a partial/guessed one."""
    engine = FlowFeatureEngine()
    release = asyncio.Event()

    async def controlled_snapshot_fetcher(symbol: str):
        await release.wait()
        return make_order_book_snapshot(symbol=symbol, last_update_id=100)

    bootstrap, _, public_connection = make_bootstrap(engine=engine, snapshot_fetcher=controlled_snapshot_fetcher)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    synchronizer = bootstrap._order_book_stream._synchronizers.get(SYMBOL)
    assert synchronizer is not None
    assert synchronizer.state in (SyncState.BUFFERING, SyncState.UNSYNCED)

    # Push a non-bridging delta while still buffering: must not be applied/published
    public_connection.push_envelope(
        depth_stream_name(SYMBOL),
        {"e": "depthUpdate", "E": _millis(NOW), "T": _millis(NOW), "s": SYMBOL, "U": 200, "u": 210, "pu": 199,
         "b": [["100.00", "1.0"]], "a": [["101.00", "1.0"]]},
    )
    await asyncio.sleep(0.03)
    assert engine.history_for(SYMBOL, ContractType.PERPETUAL).order_book.latest() == []

    # Now bridge properly and let the fetch resolve
    public_connection.push_envelope(
        depth_stream_name(SYMBOL),
        {"e": "depthUpdate", "E": _millis(NOW), "T": _millis(NOW), "s": SYMBOL, "U": 95, "u": 105, "pu": 94,
         "b": [["100.00", "1.0"]], "a": [["101.00", "1.0"]]},
    )
    await asyncio.sleep(0.02)
    release.set()
    await asyncio.sleep(0.05)

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).order_book.latest()
    assert len(retained) == 1  # exactly the materialized, applied book - never a guess

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_stop_cancels_forwarding_tasks_even_mid_wait() -> None:
    """stop() must cleanly cancel a forwarding task that is currently
    blocked awaiting the next event (the common steady-state)."""
    bootstrap, _, _ = make_bootstrap()
    await bootstrap.start()
    await asyncio.sleep(0.02)  # tasks are now parked awaiting their next event

    await asyncio.wait_for(bootstrap.stop(), timeout=2)

    assert bootstrap._tasks == {}
    assert bootstrap.health().market.status is StreamStatus.DISCONNECTED
    assert bootstrap.health().trades_task.state is TaskState.STOPPED
