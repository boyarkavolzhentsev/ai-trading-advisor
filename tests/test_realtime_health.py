"""ConnectionHealthTracker verdicts.

Uses a minimal fake transport (just ``status`` + ``stats``) rather than a
real ``WebSocketTransport`` - the tracker only depends on that shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.enums.stream import StreamStatus
from app.market_data.realtime.health import ConnectionHealthTracker

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@dataclass
class _FakeStats:
    reconnect_count: int = 0
    dropped_message_count: int = 0
    last_message_at: datetime | None = None
    last_error: str | None = None


@dataclass
class _FakeTransport:
    status: StreamStatus
    stats: _FakeStats


def test_connected_and_fresh_is_connected() -> None:
    transport = _FakeTransport(
        status=StreamStatus.CONNECTED, stats=_FakeStats(last_message_at=NOW - timedelta(seconds=1))
    )
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="agg_trade", max_silence_seconds=5.0, clock=lambda: NOW
    )
    health = tracker.snapshot()
    assert health.status is StreamStatus.CONNECTED
    assert health.provider == "binance_futures"
    assert health.stream == "agg_trade"


def test_connected_but_silent_past_threshold_becomes_degraded() -> None:
    transport = _FakeTransport(
        status=StreamStatus.CONNECTED, stats=_FakeStats(last_message_at=NOW - timedelta(seconds=60))
    )
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="depth", max_silence_seconds=5.0, clock=lambda: NOW
    )
    assert tracker.snapshot().status is StreamStatus.DEGRADED


def test_recovers_to_connected_once_fresh_again() -> None:
    transport = _FakeTransport(
        status=StreamStatus.CONNECTED, stats=_FakeStats(last_message_at=NOW - timedelta(seconds=60))
    )
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="depth", max_silence_seconds=5.0, clock=lambda: NOW
    )
    assert tracker.snapshot().status is StreamStatus.DEGRADED

    transport.stats.last_message_at = NOW - timedelta(seconds=1)
    assert tracker.snapshot().status is StreamStatus.CONNECTED


def test_never_received_anything_is_not_degraded() -> None:
    transport = _FakeTransport(status=StreamStatus.CONNECTED, stats=_FakeStats(last_message_at=None))
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="depth", max_silence_seconds=5.0, clock=lambda: NOW
    )
    assert tracker.snapshot().status is StreamStatus.CONNECTED


def test_liquidation_silence_is_not_treated_as_stale() -> None:
    """Liquidations are naturally sparse: long silence must not degrade the
    verdict when judge_by_silence is disabled for this stream kind."""
    transport = _FakeTransport(
        status=StreamStatus.CONNECTED, stats=_FakeStats(last_message_at=NOW - timedelta(hours=6))
    )
    tracker = ConnectionHealthTracker(
        transport,
        provider="binance_futures",
        stream="liquidation",
        judge_by_silence=False,
        max_silence_seconds=5.0,
        clock=lambda: NOW,
    )
    assert tracker.snapshot().status is StreamStatus.CONNECTED


def test_reconnecting_status_passes_through_unmodified_even_if_stale() -> None:
    transport = _FakeTransport(
        status=StreamStatus.RECONNECTING, stats=_FakeStats(last_message_at=NOW - timedelta(hours=1))
    )
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="depth", max_silence_seconds=5.0, clock=lambda: NOW
    )
    assert tracker.snapshot().status is StreamStatus.RECONNECTING


def test_snapshot_reports_reconnects_and_drops() -> None:
    transport = _FakeTransport(
        status=StreamStatus.CONNECTED,
        stats=_FakeStats(last_message_at=NOW, reconnect_count=3, dropped_message_count=7),
    )
    tracker = ConnectionHealthTracker(
        transport, provider="binance_futures", stream="depth", clock=lambda: NOW
    )
    health = tracker.snapshot()
    assert health.reconnect_count == 3
    assert health.dropped_message_count == 7
