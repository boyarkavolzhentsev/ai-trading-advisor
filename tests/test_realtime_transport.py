"""WebSocketTransport lifecycle, reconnect, isolation and shutdown behaviour.

Every test here runs against a fake, in-process connection - no real socket
is ever opened.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.core.enums.stream import StreamStatus
from app.market_data.realtime.reconnect import ReconnectPolicy
from app.market_data.realtime.transport import WebSocketTransport

_CLOSE_SENTINEL = object()


class FakeConnection:
    """A scriptable fake of ``websockets``' connection interface.

    Frames are pushed explicitly via :meth:`push`; the connection stays
    "open" (iteration blocks for the next frame) until :meth:`close` is
    called, exactly like a real socket.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def push(self, frame: str) -> None:
        self._queue.put_nowait(frame)

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


class ScriptedConnector:
    """Async ``connect`` callable that plays back a fixed script.

    Each script item is either an exception instance (raised) or a
    ``FakeConnection`` (returned). Calling past the end of the script raises
    ``IndexError`` - a test that does so has a logic bug, not the transport.
    """

    def __init__(self, script: list[object]) -> None:
        self._script = list(script)
        self.call_count = 0

    async def __call__(self) -> FakeConnection:
        self.call_count += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert isinstance(item, FakeConnection)
        return item


def _subscribe_message(method: str, stream_names, request_id: int) -> str:
    return json.dumps({"method": method, "params": list(stream_names), "id": request_id})


def _fast_policy() -> ReconnectPolicy:
    return ReconnectPolicy(base_seconds=0.001, factor=2.0, max_seconds=0.005)


async def _run_briefly(transport: WebSocketTransport) -> asyncio.Task[None]:
    task = asyncio.create_task(transport.run())
    await asyncio.sleep(0)  # let the task reach its first await point
    return task


async def _stop_and_finish(transport: WebSocketTransport, task: asyncio.Task[None]) -> None:
    await transport.stop()
    await asyncio.wait_for(task, timeout=1)


# --------------------------------------------------------------------------- #
# lifecycle: connect, deliver a message, shutdown
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_connect_and_receive_a_message() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    task = await _run_briefly(transport)
    connection.push(json.dumps({"stream": "btcusdt@aggTrade", "data": {"p": "1"}}))

    messages = transport.messages()
    message = await asyncio.wait_for(anext(messages), timeout=1)
    assert message.stream == "btcusdt@aggTrade"
    assert message.payload == {"p": "1"}
    assert transport.status is StreamStatus.CONNECTED

    await _stop_and_finish(transport, task)
    assert transport.status is StreamStatus.DISCONNECTED
    assert connection.closed


@pytest.mark.asyncio
async def test_graceful_shutdown_closes_the_connection_and_ends_run() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    task = await _run_briefly(transport)
    await _stop_and_finish(transport, task)

    assert connection.closed
    assert transport.status is StreamStatus.DISCONNECTED
    assert task.done()


# --------------------------------------------------------------------------- #
# subscription bookkeeping / resubscription
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_streams_subscribed_before_connect_are_sent_on_connect() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    await transport.subscribe(["btcusdt@aggTrade", "ethusdt@aggTrade"])
    task = await _run_briefly(transport)
    await asyncio.sleep(0)

    assert len(connection.sent) == 1
    sent = json.loads(connection.sent[0])
    assert sent["method"] == "SUBSCRIBE"
    assert set(sent["params"]) == {"btcusdt@aggTrade", "ethusdt@aggTrade"}

    await _stop_and_finish(transport, task)


@pytest.mark.asyncio
async def test_subscribe_while_connected_sends_immediately() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    task = await _run_briefly(transport)
    await transport.subscribe(["btcusdt@depth@100ms"])

    assert len(connection.sent) == 1
    sent = json.loads(connection.sent[0])
    assert sent["method"] == "SUBSCRIBE"
    assert sent["params"] == ["btcusdt@depth@100ms"]

    await _stop_and_finish(transport, task)


@pytest.mark.asyncio
async def test_unsubscribe_while_connected_sends_immediately() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    await transport.subscribe(["btcusdt@aggTrade"])
    task = await _run_briefly(transport)
    await asyncio.sleep(0)
    connection.sent.clear()

    await transport.unsubscribe(["btcusdt@aggTrade"])
    assert len(connection.sent) == 1
    sent = json.loads(connection.sent[0])
    assert sent["method"] == "UNSUBSCRIBE"
    assert sent["params"] == ["btcusdt@aggTrade"]
    assert transport.desired_streams == frozenset()

    await _stop_and_finish(transport, task)


@pytest.mark.asyncio
async def test_reconnect_replays_desired_subscriptions() -> None:
    first = FakeConnection()
    second = FakeConnection()
    connector = ScriptedConnector([first, second])
    transport = WebSocketTransport(
        connector, build_subscribe_message=_subscribe_message, reconnect_policy=_fast_policy()
    )

    await transport.subscribe(["btcusdt@aggTrade"])
    task = await _run_briefly(transport)
    await asyncio.sleep(0)
    assert len(first.sent) == 1

    await first.close()  # simulate the server dropping the connection
    await asyncio.sleep(0.02)  # allow the reconnect loop to run

    assert len(second.sent) == 1
    assert json.loads(second.sent[0])["params"] == ["btcusdt@aggTrade"]
    assert transport.stats.reconnect_count >= 1

    await _stop_and_finish(transport, task)


# --------------------------------------------------------------------------- #
# reconnect / backoff on connect failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_connect_failures_trigger_backoff_then_succeed() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([ConnectionRefusedError("refused"), OSError("still down"), connection])
    transport = WebSocketTransport(
        connector,
        build_subscribe_message=_subscribe_message,
        reconnect_policy=_fast_policy(),
        random_jitter=lambda: 0.0,
    )

    task = asyncio.create_task(transport.run())
    connection.push(json.dumps({"stream": "btcusdt@aggTrade", "data": {"ok": True}}))
    messages = transport.messages()
    message = await asyncio.wait_for(anext(messages), timeout=1)

    assert message.payload == {"ok": True}
    assert connector.call_count == 3
    assert transport.stats.reconnect_count >= 1
    assert transport.stats.last_error is not None

    await _stop_and_finish(transport, task)


@pytest.mark.asyncio
async def test_a_programming_error_from_connect_is_not_swallowed() -> None:
    """Only ``connection_errors`` are treated as reconnectable; anything else
    is a bug and must propagate out of the task, not be silently retried."""

    class NotAConnectionError(Exception):
        pass

    connector = ScriptedConnector([NotAConnectionError("boom")])
    transport = WebSocketTransport(
        connector,
        build_subscribe_message=_subscribe_message,
        connection_errors=(OSError,),
        reconnect_policy=_fast_policy(),
    )

    with pytest.raises(NotAConnectionError):
        await asyncio.wait_for(transport.run(), timeout=1)


# --------------------------------------------------------------------------- #
# malformed message isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_malformed_frame_is_isolated_and_does_not_stop_the_loop() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    task = await _run_briefly(transport)
    connection.push("not valid json {{{")
    connection.push(json.dumps({"stream": "btcusdt@aggTrade", "data": {"p": "2"}}))

    messages = transport.messages()
    message = await asyncio.wait_for(anext(messages), timeout=1)

    assert message.payload == {"p": "2"}
    assert transport.stats.parse_error_count == 1

    await _stop_and_finish(transport, task)


@pytest.mark.asyncio
async def test_control_ack_without_stream_key_is_not_routed_but_keeps_connection_alive() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(connector, build_subscribe_message=_subscribe_message)

    task = await _run_briefly(transport)
    connection.push(json.dumps({"result": None, "id": 1}))  # SUBSCRIBE ack, no "stream"/"data"
    connection.push(json.dumps({"stream": "btcusdt@aggTrade", "data": {"p": "3"}}))

    messages = transport.messages()
    message = await asyncio.wait_for(anext(messages), timeout=1)
    assert message.payload == {"p": "3"}

    await _stop_and_finish(transport, task)


# --------------------------------------------------------------------------- #
# bounded queue / slow consumer isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_queue_overflow_drops_oldest_and_counts_it() -> None:
    connection = FakeConnection()
    connector = ScriptedConnector([connection])
    transport = WebSocketTransport(
        connector, build_subscribe_message=_subscribe_message, queue_maxsize=2
    )

    task = await _run_briefly(transport)
    for i in range(5):
        connection.push(json.dumps({"stream": "btcusdt@aggTrade", "data": {"i": i}}))
    await asyncio.sleep(0.01)  # let the read loop drain all pushed frames without a consumer

    assert transport.stats.dropped_message_count == 3

    messages = transport.messages()
    remaining = [
        (await asyncio.wait_for(anext(messages), timeout=1)).payload["i"] for _ in range(2)
    ]
    assert remaining == [3, 4]  # the two most recent survive

    await _stop_and_finish(transport, task)
