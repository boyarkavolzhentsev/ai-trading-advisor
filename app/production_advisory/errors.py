"""Stage 0D Production Advisory Composition operational errors.

Every error here is composition/operational semantics only - never a
trading-domain verdict, and never mixed with ``RuntimeCycleOutcome``/
``FinalRecommendationOutcome``/any Stage 5-9 block reason. No HTTP
dependency, no status code: mapping these to a transport-level response is
the future Application layer's job, not this one's.
"""

from __future__ import annotations


class ProductionAdvisoryError(Exception):
    """Base for every Stage 0D composition-level operational error."""


class ProductionAdvisoryLifecycleError(ProductionAdvisoryError):
    """Raised on a lifecycle-contract violation: ``run_cycle()`` called
    before a successful ``startup()`` or after ``shutdown()``, or
    ``startup()`` called after ``shutdown()``.

    ``startup()``/``shutdown()`` are otherwise idempotent (calling either
    again from its own already-reached state is a safe no-op) - only these
    two out-of-order transitions are deterministic failures, per the
    approved smallest-lifecycle-guard closure: NEW -> STARTED (via
    ``startup()``) -> STOPPED (via ``shutdown()``), no cycle outside
    STARTED, no restart after STOPPED.
    """


class ProductionAdvisoryDuplicateCycleError(ProductionAdvisoryError):
    """Raised by the duplicate-cycle preflight, before ``run_runtime_cycle``
    is ever called, whenever any caller-supplied ``trade_id`` already has
    persisted tracking and/or provenance state (anything other than
    ``"ABSENT"`` in either store).

    Deliberately includes the case where a prior attempt persisted state but
    crashed before returning a result to its caller - safety over
    transparent replay (see the approved retry/idempotency design closure).
    No ``ProductionAdvisoryCycleResult`` is ever constructed when this is
    raised.

    ``colliding_trade_ids`` is a normalized, deterministic, sorted tuple
    (never a set/dict whose iteration order could vary between processes)
    so a future Application layer can log/report it reproducibly.
    """

    def __init__(self, colliding_trade_ids: tuple[str, ...]) -> None:
        self.colliding_trade_ids: tuple[str, ...] = tuple(sorted(set(colliding_trade_ids)))
        super().__init__(
            "duplicate cycle: trade_id(s) already have persisted state: " + ", ".join(self.colliding_trade_ids)
        )


__all__ = ["ProductionAdvisoryDuplicateCycleError", "ProductionAdvisoryError", "ProductionAdvisoryLifecycleError"]
