"""FastAPI dependency-injection seam for the shared ``ApplicationAdvisoryService``.

Never constructs a service - only reads back the single instance ``lifespan``
(see ``app.api.main``) already stored on ``app.state``. Overridable in tests
via ``app.dependency_overrides[get_advisory_service]``."""

from __future__ import annotations

from fastapi import Request

from app.application.advisory_service import ApplicationAdvisoryService


def get_advisory_service(request: Request) -> ApplicationAdvisoryService:
    return request.app.state.advisory_service


__all__ = ["get_advisory_service"]
