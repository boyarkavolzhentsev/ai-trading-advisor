"""Real-time stream connection status enum."""

from __future__ import annotations

from enum import StrEnum


class StreamStatus(StrEnum):
    """Lifecycle/freshness status of one real-time market data stream.

    ``DEGRADED`` is layered on top of ``CONNECTED`` by a health tracker when
    a stream that is expected to push continuously has gone quiet longer
    than its freshness threshold - it is never applied to naturally sparse
    streams (e.g. liquidations) merely because nothing has happened.
    """

    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
