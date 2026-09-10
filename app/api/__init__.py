"""FastAPI transport layer above ``app.application.ApplicationAdvisoryService``.

Transport-only: no trading/decision logic, no direct MT5/Binance/OpenAI
import, no direct ``ProductionAdvisoryComposer``/``ProductionAdvisoryConfig``
import - the one narrow exception being ``app.bootstrap.production``'s own
factory function, called (never constructed piecemeal) only inside
``app.api.main``'s ``lifespan``. See ``app.api.main`` for the app factory and
``app.bootstrap.production`` for the composition root."""

from __future__ import annotations

__all__: list[str] = []
