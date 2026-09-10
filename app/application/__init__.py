"""Transport-neutral Application Service + DTO layer, directly above
``app.production_advisory.composer.ProductionAdvisoryComposer``.

No FastAPI/Telegram/HTTP dependency lives here or anywhere downstream of it -
see ``app.application.advisory_service``'s own module docstring."""

from __future__ import annotations

__all__: list[str] = []
