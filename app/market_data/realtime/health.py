"""Connection health tracking and freshness verdicts.

Wraps anything exposing ``status``/``stats`` (a ``WebSocketTransport``, or a
fake in tests) plus a per-stream freshness policy to produce an immutable
``StreamHealth`` snapshot on demand - the same "verdict built when asked"
posture as ``DataQualityValidator``. This module never repairs or retries
anything; it only judges.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.core.enums.stream import StreamStatus
from app.core.models.stream_health import StreamHealth


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _TransportStatsLike(Protocol):
    reconnect_count: int
    dropped_message_count: int
    last_message_at: datetime | None
    last_error: str | None


class _TransportLike(Protocol):
    status: StreamStatus
    stats: _TransportStatsLike


class ConnectionHealthTracker:
    """Produces ``StreamHealth`` snapshots for one logical stream.

    ``judge_by_silence`` controls whether long message silence degrades the
    verdict: streams that push continuously in an active market (trades,
    depth, mark price) should be judged this way; naturally sparse streams
    (liquidations) must not be flagged stale merely because nothing has
    happened - set ``judge_by_silence=False`` for those, so only the
    connection's own status drives the verdict.
    """

    def __init__(
        self,
        transport: _TransportLike,
        *,
        provider: str,
        stream: str,
        symbol: str | None = None,
        judge_by_silence: bool = True,
        max_silence_seconds: float = 30.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._transport = transport
        self._provider = provider
        self._stream = stream
        self._symbol = symbol
        self._judge_by_silence = judge_by_silence
        self._max_silence = max_silence_seconds
        self._clock = clock or _utc_now

    def snapshot(self) -> StreamHealth:
        """Build the current health verdict. Cheap; call as often as needed."""
        now = self._clock()
        status = self._transport.status
        if status is StreamStatus.CONNECTED and self._judge_by_silence and self._is_stale(now):
            status = StreamStatus.DEGRADED
        return StreamHealth(
            provider=self._provider,
            stream=self._stream,
            symbol=self._symbol,
            status=status,
            last_message_at=self._transport.stats.last_message_at,
            last_error=self._transport.stats.last_error,
            reconnect_count=self._transport.stats.reconnect_count,
            dropped_message_count=self._transport.stats.dropped_message_count,
            checked_at=now,
        )

    def _is_stale(self, now: datetime) -> bool:
        last = self._transport.stats.last_message_at
        if last is None:
            return False  # freshly connected, hasn't had a chance to receive anything yet
        return (now - last).total_seconds() > self._max_silence


__all__ = ["ConnectionHealthTracker"]
