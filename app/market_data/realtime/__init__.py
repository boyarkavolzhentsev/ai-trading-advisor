"""Provider-agnostic real-time market data infrastructure.

Layering (outside in), mirroring ``app.market_data``'s REST layering:

1. ``transport`` - WebSocket connection lifecycle, reconnect/backoff,
   subscription bookkeeping. No provider or domain knowledge.
2. ``router`` - dispatches raw messages to provider-specific mappers by
   stream name, producing domain events.
3. ``order_book_sync`` / ``taker_flow`` - deterministic stateful assembly of
   domain events into a maintained order book / rolling taker-flow buckets.
4. ``buffers`` / ``health`` - bounded recent-history storage and
   connection freshness verdicts.

Application code depends on ``app.market_data.realtime.protocols`` and the
domain models, never on a concrete venue's WebSocket wiring.
"""

from __future__ import annotations
