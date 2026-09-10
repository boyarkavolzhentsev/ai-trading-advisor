"""Telegram operator transport above ``ApplicationAdvisoryService``.

Operator-only: never executes trades, places/cancels orders, modifies
positions, or accepts an arbitrary symbol. Calls
``app.application.advisory_service.ApplicationAdvisoryService`` directly,
in-process - never over FastAPI/HTTP, never re-serializing ``AdvisoryResponse``
through JSON.

See ``app.telegram.bot`` for the testable app factory (``build_bot``) and the
production runner (``run``); ``app.telegram.config``/``identity``/
``rendering``/``handlers`` are each focused, mostly-pure modules this
package composes.
"""

from __future__ import annotations

__all__: list[str] = []
