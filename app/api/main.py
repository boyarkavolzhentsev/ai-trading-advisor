"""FastAPI app factory and the two approved V1 routes.

``create_app`` is the primary testability seam (see the approved FastAPI
design closure, "14. APP FACTORY"): pass ``service=`` a fake
``ApplicationAdvisoryService`` for tests, or omit it entirely for production,
in which case the real one is built lazily - inside ``lifespan``, never at
import time or at ``create_app()`` call time - by
``app.bootstrap.production.build_production_advisory_service``. Merely
importing this module or calling ``create_app(service=fake)`` never reads an
environment variable, never touches MT5/Binance/OpenAI, and never
constructs a ``ProductionAdvisoryComposer``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status

from app.api.dependencies import get_advisory_service
from app.api.exception_handlers import register_exception_handlers
from app.api.models import AdvisoryRequest, ErrorResponse, HealthResponse
from app.application.advisory_service import ApplicationAdvisoryService
from app.application.dto import AdvisoryResponse, ApplicationAdvisoryStatus
from app.bootstrap.production import build_production_advisory_service


def create_app(*, service: ApplicationAdvisoryService | None = None) -> FastAPI:
    """``service=None`` (production mode) defers every environment read and
    every object construction to ``lifespan`` startup - never to this
    function call itself. ``service=<fake>`` (test mode) uses that exact
    injected instance, with the identical one-startup/one-shutdown lifecycle,
    and never calls ``build_production_advisory_service`` at all."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned_service = service if service is not None else build_production_advisory_service()
        await owned_service.startup()
        app.state.advisory_service = owned_service
        try:
            yield
        finally:
            await owned_service.shutdown()

    app = FastAPI(lifespan=lifespan)
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Process/API liveness only - never calls ``create_advisory``, MT5,
        Binance, OpenAI, or the calendar bridge."""
        return HealthResponse()

    @app.post(
        "/v1/advisory",
        response_model=AdvisoryResponse,
        responses={
            # 503 here documents ONLY the structured
            # ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE case (this route
            # returning its own response_model with a mutated status code).
            # ApplicationStateError's own 503 (a distinct, ErrorResponse-
            # shaped body, produced by a global exception handler - see
            # app.api.exception_handlers) is NOT representable in this
            # per-route `responses=` declaration: OpenAPI 3's `responses`
            # dict holds exactly one schema per status code, and a global
            # exception handler is invisible to a route's own decorator.
            # This is a known, accepted static-documentation limitation -
            # never a runtime conflation: the two 503 bodies remain
            # genuinely distinct at the actual HTTP response level (see
            # tests/test_api_module_hygiene.py's own dedicated non-
            # conflation test).
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": AdvisoryResponse},
            # FastAPI's own default 422 documentation (HTTPValidationError)
            # does not match this app's actual runtime body - a global
            # exception handler rewrites every RequestValidationError into
            # this app's own ErrorResponse envelope (see
            # app.api.exception_handlers). Overridden here so the
            # documented schema matches what the API actually returns.
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
            status.HTTP_409_CONFLICT: {"model": ErrorResponse},
            status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
        },
    )
    async def create_advisory(
        request: AdvisoryRequest,
        response: Response,
        advisory_service: ApplicationAdvisoryService = Depends(get_advisory_service),
    ) -> AdvisoryResponse:
        """Exactly one ``create_advisory`` call, no retry, no generated
        fallback identity, no symbol argument. ``response.status_code`` is
        the only thing mutated for ``SERVICE_UNAVAILABLE`` - the returned
        body stays the full, unmodified ``AdvisoryResponse``, still filtered/
        serialized through the declared ``response_model``."""
        result = await advisory_service.create_advisory(logical_cycle_id=request.logical_cycle_id)
        if result.status is ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return result

    return app


app = create_app()


__all__ = ["app", "create_app"]
