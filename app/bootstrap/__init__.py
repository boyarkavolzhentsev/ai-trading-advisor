"""Production composition root.

The only place in this repository allowed to assemble the real
``ProductionAdvisoryConfig`` / ``ProductionAdvisoryComposer`` /
``ApplicationAdvisoryService`` object graph from environment variables. See
``app.bootstrap.production`` for the two exposed factory functions.

Never calls ``.startup()``/``.shutdown()``/``.run_cycle()`` on anything it
constructs - lifecycle ownership belongs exclusively to whichever caller
(FastAPI ``lifespan``, a future Telegram adapter) actually starts serving
requests."""

from __future__ import annotations

__all__: list[str] = []
