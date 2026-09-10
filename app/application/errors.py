"""Application-layer transport-neutral errors.

Every error here is Application-composition operational semantics only -
mirrors ``app.production_advisory.errors``'s own discipline one layer up: no
HTTP status code, no transport dependency of any kind. Mapping these to a
transport-level response (FastAPI status codes, Telegram error replies) is a
future adapter's job, never this module's.

There is deliberately no ``ServiceUnavailableError``: a Stage0D cycle
reporting ``ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE`` already
returns a valid, fully-typed ``ProductionAdvisoryCycleResult`` - not an
exception - so the Application layer preserves that as structured
``AdvisoryResponse`` output (``status=SERVICE_UNAVAILABLE``), never raises
for it (see ``app.application.advisory_service``).
"""

from __future__ import annotations


class ApplicationAdvisoryError(Exception):
    """Base for every Application-layer advisory error."""


class DuplicateCycleError(ApplicationAdvisoryError):
    """Maps ``ProductionAdvisoryDuplicateCycleError`` unchanged: the same
    ``logical_cycle_id`` was already attempted (its derived ``trade_ids``
    already have persisted tracking/provenance state). Never regenerates a
    new identity on the caller's behalf - a duplicate retry must surface this
    error, not silently become a fresh cycle."""

    def __init__(self, *, logical_cycle_id: str, colliding_trade_ids: tuple[str, ...]) -> None:
        self.logical_cycle_id = logical_cycle_id
        self.colliding_trade_ids = colliding_trade_ids
        super().__init__(
            f"duplicate cycle for logical_cycle_id={logical_cycle_id!r}: "
            f"trade_id(s) already have persisted state: {', '.join(colliding_trade_ids)}"
        )


class ApplicationStateError(ApplicationAdvisoryError):
    """Maps ``ProductionAdvisoryLifecycleError``: ``create_advisory()``
    called before ``startup()`` or after ``shutdown()``, or ``startup()``
    called after ``shutdown()``."""


class ApplicationInputError(ApplicationAdvisoryError):
    """The caller supplied an invalid ``logical_cycle_id`` (fails
    ``app.application.identity.validate_logical_cycle_id``). The only
    caller-input error in this package - ``composer.run_cycle`` is never
    reached when this is raised."""


class InternalApplicationError(ApplicationAdvisoryError):
    """An Application-layer programming defect or unexpected exception -
    never caller input. Covers Stage0D's own trade-ID-coverage ``ValueError``
    occurring despite a valid, fully-derived ``trade_ids`` mapping (which
    should never happen by construction - see ``app.application.identity``)
    and any other unexpected exception. The outward message is always a safe,
    generic string; the original exception is chained via ``raise ... from
    exc`` for logging only, never copied verbatim into this error's own
    message (which could otherwise leak MT5 credentials/OpenAI config repr
    content)."""


__all__ = [
    "ApplicationAdvisoryError",
    "ApplicationInputError",
    "ApplicationStateError",
    "DuplicateCycleError",
    "InternalApplicationError",
]
