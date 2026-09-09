"""Stage 0D process-local cycle serialization.

V1 requires exactly one advisory cycle executing at a time within this
process: shared Flow realtime state, recommendation persistence, and MT5
reads must never be exercised by two overlapping cycles. No distributed
locking, no file lock - a plain ``asyncio.Lock`` is the smallest primitive
that satisfies this within one process/one event loop, mirroring the same
single-event-loop invariant ``app.flow.realtime_bootstrap`` already
mandates for Stage 0A.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Self


class ProductionAdvisoryCycleLock:
    """Async-context-manager wrapper around one ``asyncio.Lock``.

    ``async with lock:`` always releases on both the success and the
    exception path - ``asyncio.Lock`` already guarantees this via its own
    context-manager protocol (``__aexit__`` unconditionally releases); this
    class exists only to give that guarantee a Stage0D-specific,
    self-documenting name rather than exposing a bare ``asyncio.Lock`` on
    the composer.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        await self._lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.release()

    @property
    def locked(self) -> bool:
        """Point-in-time inspection only - never used to decide business
        logic, only for operational diagnostics/tests."""
        return self._lock.locked()


__all__ = ["ProductionAdvisoryCycleLock"]
