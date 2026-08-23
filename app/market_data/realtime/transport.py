"""Generic asyncio WebSocket transport.

No provider knowledge, no domain models, no trading logic: this only knows
how to keep one logical WebSocket connection alive, decode text frames into
``RawStreamMessage``, and track which stream names should be subscribed so a
reconnect can replay them. Provider-specific URL/message-shape details and
exception types are injected by the caller (see
``app.market_data.providers.binance.futures.realtime.transport``).

Failure isolation:

- A malformed frame (bad JSON) is counted and skipped; it never ends the
  read loop.
- Only the exception types the caller declares via ``connection_errors`` are
  treated as "the connection died, back off and retry" - anything else is a
  programming error and is deliberately left to propagate out of ``run()``,
  where it fails only *this* transport's task, not the whole process.
- A slow consumer never blocks the socket read loop: the outgoing queue is
  bounded and overflows by dropping the oldest queued message, counted in
  ``stats.dropped_message_count``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.enums.stream import StreamStatus
from app.market_data.realtime.messages import RawStreamMessage
from app.market_data.realtime.reconnect import ReconnectPolicy

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _default_jitter() -> float:
    return random.random()  # noqa: S311 - reconnect spacing, not security-sensitive


def _default_unwrap(payload: Any) -> tuple[str | None, Any]:
    """Unwrap the common ``{"stream": ..., "data": ...}`` combined-stream envelope.

    Returns ``(None, payload)`` for anything else (e.g. a SUBSCRIBE
    acknowledgement), signalling "nothing to route, but the connection is
    alive".
    """
    if isinstance(payload, dict) and "stream" in payload and "data" in payload:
        return payload["stream"], payload["data"]
    return None, payload


class WebSocketConnection(Protocol):
    """What the transport needs from an open connection.

    Satisfied by ``websockets.asyncio.client.ClientConnection`` without this
    module importing ``websockets`` directly - tests inject a fake instead.
    """

    async def send(self, message: str) -> None: ...
    def __aiter__(self) -> AsyncIterator[str]: ...
    async def close(self) -> None: ...


ConnectFn = Callable[[], Awaitable[WebSocketConnection]]
SubscribeMessageBuilder = Callable[[str, Sequence[str], int], str]
UnwrapFn = Callable[[Any], tuple[str | None, Any]]


@dataclass(slots=True)
class TransportStats:
    """Mutable counters a health tracker (or a test) can read."""

    reconnect_count: int = 0
    dropped_message_count: int = 0
    parse_error_count: int = 0
    last_message_at: datetime | None = None
    last_error: str | None = None


class WebSocketTransport:
    """Keeps one logical, multiplexed WebSocket connection alive.

    Consumers pull decoded-but-unmapped events via :meth:`messages`. Desired
    subscriptions are tracked locally so a reconnect can replay them without
    the caller having to resubscribe manually.
    """

    def __init__(
        self,
        connect: ConnectFn,
        *,
        build_subscribe_message: SubscribeMessageBuilder,
        connection_errors: tuple[type[BaseException], ...] = (OSError,),
        unwrap: UnwrapFn = _default_unwrap,
        reconnect_policy: ReconnectPolicy | None = None,
        queue_maxsize: int = 1000,
        random_jitter: Callable[[], float] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connect = connect
        self._build_subscribe_message = build_subscribe_message
        self._connection_errors = connection_errors
        self._unwrap = unwrap
        self._policy = reconnect_policy or ReconnectPolicy()
        self._queue: asyncio.Queue[RawStreamMessage] = asyncio.Queue(maxsize=queue_maxsize)
        self._random_jitter = random_jitter or _default_jitter
        self._clock = clock or _utc_now
        self.stats = TransportStats()
        self._desired_streams: set[str] = set()
        self._connection: WebSocketConnection | None = None
        self._stop_event = asyncio.Event()
        self._next_request_id = 1
        self._status = StreamStatus.DISCONNECTED

    @property
    def status(self) -> StreamStatus:
        return self._status

    @property
    def desired_streams(self) -> frozenset[str]:
        return frozenset(self._desired_streams)

    async def run(self) -> None:
        """Run the connect/read/reconnect loop until :meth:`stop` is called.

        Intended to be scheduled as its own ``asyncio.Task``; a genuine bug
        surfacing from within (anything not in ``connection_errors`` or the
        narrowly-scoped JSON-decode guard) ends only that task.
        """
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            self._status = StreamStatus.CONNECTING if attempt == 1 else StreamStatus.RECONNECTING
            try:
                connection = await self._connect()
            except self._connection_errors as exc:
                self._record_failure(exc)
                delay = self._policy.delay_for_attempt(attempt, jitter=self._random_jitter())
                logger.warning("connect attempt %d failed: %s; retrying in %.2fs", attempt, exc, delay)
                await self._interruptible_sleep(delay)
                continue

            self._connection = connection
            self._status = StreamStatus.CONNECTED
            if attempt > 1:
                self.stats.reconnect_count += 1
            received_any = False
            try:
                await self._resubscribe_all()
                received_any = await self._read_loop()
            except self._connection_errors as exc:
                self._record_failure(exc)
            finally:
                await self._safe_close()

            if self._stop_event.is_set():
                break
            attempt = 0 if received_any else attempt
        self._status = StreamStatus.DISCONNECTED

    async def stop(self) -> None:
        """Signal shutdown and close the current connection, if any."""
        self._stop_event.set()
        await self._safe_close()

    async def subscribe(self, stream_names: Sequence[str]) -> None:
        """Add stream names to the desired set, subscribing immediately if connected."""
        new = [name for name in stream_names if name not in self._desired_streams]
        self._desired_streams.update(stream_names)
        if new and self._connection is not None:
            await self._send_control("SUBSCRIBE", new)

    async def unsubscribe(self, stream_names: Sequence[str]) -> None:
        """Remove stream names from the desired set, unsubscribing immediately if connected."""
        existing = [name for name in stream_names if name in self._desired_streams]
        self._desired_streams.difference_update(stream_names)
        if existing and self._connection is not None:
            await self._send_control("UNSUBSCRIBE", existing)

    async def messages(self) -> AsyncIterator[RawStreamMessage]:
        """Yield routed-ready messages as they arrive. Runs until cancelled."""
        while True:
            yield await self._queue.get()

    def _record_failure(self, exc: BaseException) -> None:
        self.stats.last_error = f"{type(exc).__name__}: {exc}"

    async def _resubscribe_all(self) -> None:
        if self._desired_streams:
            await self._send_control("SUBSCRIBE", sorted(self._desired_streams))

    async def _send_control(self, method: str, stream_names: Sequence[str]) -> None:
        assert self._connection is not None
        request_id = self._next_request_id
        self._next_request_id += 1
        message = self._build_subscribe_message(method, stream_names, request_id)
        await self._connection.send(message)

    async def _read_loop(self) -> bool:
        assert self._connection is not None
        received_any = False
        async for raw_text in self._connection:
            try:
                payload = json.loads(raw_text)
            except (json.JSONDecodeError, TypeError) as exc:
                self.stats.parse_error_count += 1
                logger.warning("malformed frame ignored: %s", exc)
                continue
            received_any = True
            stream_name, data = self._unwrap(payload)
            if stream_name is None:
                continue  # control ack or unrecognized envelope: connection is alive, nothing to route
            message = RawStreamMessage(stream=stream_name, payload=data, received_at=self._clock())
            self.stats.last_message_at = message.received_at
            self._enqueue(message)
        return received_any

    def _enqueue(self, message: RawStreamMessage) -> None:
        try:
            self._queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass
        try:
            self._queue.get_nowait()
            self.stats.dropped_message_count += 1
        except asyncio.QueueEmpty:
            pass
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            pass  # extremely unlikely race with a concurrent consumer; already counted

    async def _interruptible_sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _safe_close(self) -> None:
        if self._connection is not None:
            connection, self._connection = self._connection, None
            try:
                await connection.close()
            except self._connection_errors:
                pass


__all__ = ["TransportStats", "WebSocketConnection", "WebSocketTransport"]
