"""FastAPI exception -> stable ``ErrorResponse`` mapping.

Every handler here returns the identical envelope shape
(``{"error": {...}}``) - never a raw exception, traceback, or provider
payload. ``ApplicationInputError``, ``ApplicationStateError``,
``InternalApplicationError``, and any un-typed ``Exception`` all use a fixed,
content-independent message - never ``str(exc)`` - per the pre-commit
security review's corrected policy: this is deliberately NOT "safe because
today's Application-layer/identity-validation messages happen to be
sanitized/bounded" (``app.application.identity.validate_logical_cycle_id``
embeds the caller's rejected, arbitrary, request-body value verbatim into
``ApplicationInputError``'s own message) - it is a policy that holds
regardless of what any upstream message currently contains. Only ``DuplicateCycleError`` exposes any per-request content
(``logical_cycle_id``/``colliding_trade_ids``), and both are proven
bounded/filesystem-safe by construction (see its own handler docstring
below) - every other handler's message is a fixed literal.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.models import ErrorCode, ErrorDetail, ErrorResponse
from app.application.errors import (
    ApplicationInputError,
    ApplicationStateError,
    DuplicateCycleError,
    InternalApplicationError,
)

_INTERNAL_ERROR_MESSAGE = "An internal application error occurred."
_INVALID_LOGICAL_CYCLE_ID_MESSAGE = "Invalid logical_cycle_id."
_APPLICATION_STATE_ERROR_MESSAGE = "Application service is unavailable."


def _error_response(detail: ErrorDetail, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=jsonable_encoder(ErrorResponse(error=detail)))


async def _handle_application_input_error(request: Request, exc: ApplicationInputError) -> JSONResponse:
    """Never ``str(exc)``: ``app.application.identity.validate_logical_cycle_id``
    embeds the caller's rejected value verbatim (via ``{logical_cycle_id!r}``)
    into its message, and that value is arbitrary, caller-controlled, request-
    body content that reached this point specifically because it failed
    validation - it must never be reflected back into the HTTP response
    merely because the Application-layer exception currently happens to
    contain it. Always the fixed, content-independent literal instead
    (pre-commit security review, "1. APPLICATION INPUT ERROR - HTTP ECHO
    SAFETY")."""
    return _error_response(
        ErrorDetail(code=ErrorCode.APPLICATION_INPUT_ERROR, message=_INVALID_LOGICAL_CYCLE_ID_MESSAGE),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _handle_duplicate_cycle_error(request: Request, exc: DuplicateCycleError) -> JSONResponse:
    """``logical_cycle_id``/``colliding_trade_ids`` are safe to expose
    verbatim - never a persistence path or exception cause. Bounded and
    filesystem-safe by construction, not merely by convention:
    ``DuplicateCycleError`` is only ever raised from a
    ``ProductionAdvisoryDuplicateCycleError`` whose ``colliding_trade_ids``
    are drawn exclusively from the ``trade_ids`` mapping
    ``app.application.identity.derive_trade_ids`` derived from THIS
    request's own ``logical_cycle_id`` - which already passed
    ``validate_logical_cycle_id``'s ``[A-Za-z0-9_-]{1,128}`` regex before
    ``create_advisory`` ever called the composer. Every colliding trade_id
    therefore matches ``f"{logical_cycle_id}__{family.value}"`` for one of
    the four fixed ``StrategyFamily`` values - at most 128 + 2 + 15 = 145
    ASCII characters, no path separator, no colon, no traversal token."""
    return _error_response(
        ErrorDetail(
            code=ErrorCode.DUPLICATE_CYCLE,
            message=str(exc),
            logical_cycle_id=exc.logical_cycle_id,
            colliding_trade_ids=exc.colliding_trade_ids,
        ),
        status.HTTP_409_CONFLICT,
    )


async def _handle_application_state_error(request: Request, exc: ApplicationStateError) -> JSONResponse:
    """Never ``str(exc)``: although today's content is only Stage0D's own
    fixed lifecycle-guard wording, a public wire contract must not depend on
    that internal implementation text remaining unchanged forever - a fixed,
    content-independent literal instead (pre-commit security review, "4.
    APPLICATION STATE ERROR")."""
    return _error_response(
        ErrorDetail(code=ErrorCode.APPLICATION_STATE_ERROR, message=_APPLICATION_STATE_ERROR_MESSAGE),
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


async def _handle_internal_application_error(request: Request, exc: InternalApplicationError) -> JSONResponse:
    """Never ``str(exc)`` - always the fixed literal, regardless of what
    this exception's current message happens to contain."""
    return _error_response(
        ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=_INTERNAL_ERROR_MESSAGE),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def _handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI/Pydantic's own request-body validation failure (e.g. a
    missing ``logical_cycle_id`` or a forbidden extra field) - a stable,
    sanitized envelope rather than pydantic's internal validator-error
    graph."""
    return _error_response(
        ErrorDetail(code=ErrorCode.APPLICATION_INPUT_ERROR, message="Invalid request."),
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    """Defense-in-depth catch-all for anything that escapes the Application
    layer's own catch-all unswallowed - never ``str(exc)``/``repr(exc)``/a
    traceback/a cause, since an escaped raw exception carries no
    sanitization guarantee at all."""
    return _error_response(
        ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=_INTERNAL_ERROR_MESSAGE),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationInputError, _handle_application_input_error)
    app.add_exception_handler(DuplicateCycleError, _handle_duplicate_cycle_error)
    app.add_exception_handler(ApplicationStateError, _handle_application_state_error)
    app.add_exception_handler(InternalApplicationError, _handle_internal_application_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_exception)


__all__ = ["register_exception_handlers"]
