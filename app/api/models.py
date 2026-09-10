"""HTTP-only request/error models.

These are transport-layer concerns only - never re-declarations of anything
in ``app.application.dto``. The advisory response itself is
``app.application.dto.AdvisoryResponse``, used directly as the FastAPI
``response_model`` (see ``app.api.main``) - no duplicate HTTP DTO exists for
it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AdvisoryRequest(BaseModel):
    """The sole POST /v1/advisory request body. ``extra=\"forbid\"`` rejects
    any additional field outright (including a ``symbol`` field) - V1 has no
    arbitrary symbol switching. The ``logical_cycle_id`` regex is
    deliberately NOT duplicated here - ``app.application.identity.
    validate_logical_cycle_id`` remains the sole authoritative validation
    boundary; a syntactically-present-but-semantically-invalid value reaches
    the Application layer and raises ``ApplicationInputError`` there."""

    model_config = ConfigDict(extra="forbid")

    logical_cycle_id: str


class HealthResponse(BaseModel):
    """GET /health's entire response body - process/API liveness only, never
    a market/provider health probe."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"


class ErrorCode(StrEnum):
    """Stable wire error codes - never derived from a Python exception
    class's ``__name__`` dynamically, so a future rename can never silently
    change the wire contract."""

    APPLICATION_INPUT_ERROR = "APPLICATION_INPUT_ERROR"
    DUPLICATE_CYCLE = "DUPLICATE_CYCLE"
    APPLICATION_STATE_ERROR = "APPLICATION_STATE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    """``logical_cycle_id``/``colliding_trade_ids`` are populated only for
    ``DUPLICATE_CYCLE`` - both are already-sanitized, caller-derived identity
    strings (never a persistence path, exception cause, or provider
    payload)."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    logical_cycle_id: str | None = None
    colliding_trade_ids: tuple[str, ...] = ()


class ErrorResponse(BaseModel):
    """The one stable error envelope every non-2xx/non-503-advisory response
    uses."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


__all__ = ["AdvisoryRequest", "ErrorCode", "ErrorDetail", "ErrorResponse", "HealthResponse"]
