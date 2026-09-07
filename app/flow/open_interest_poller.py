"""Stage 0A REST open-interest poller.

Open interest has no public Binance WebSocket stream (see
``app.flow.open_interest``'s own docstring: "every observation is a REST
poll"). This module is the smallest isolated production component that
periodically calls the existing, unmodified REST capability
(``BinanceFuturesMarketDataProvider.get_open_interest``/``app.mt5``-style
protocol below) and feeds each successfully observed, unmodified
``OpenInterest`` model into the existing, unmodified
``FlowFeatureEngine.record_open_interest``.

No new ``OpenInterest`` model, no new ``FeatureQuality``/status vocabulary:
a temporary provider failure (``MarketDataError``) is logged and skipped -
never converted into a fabricated/zero observation. The engine's last real
observation ages naturally; ``app.flow.open_interest``'s own existing
staleness threshold (``DEFAULT_MAX_STALENESS``) is what decides when it
becomes ``STALE``, unchanged by anything here. An unexpected
(non-``MarketDataError``) exception is never swallowed - it propagates out
of the background poll task, ending only this poller's own task, mirroring
``WebSocketTransport.run()``'s own "a genuine bug fails only this task, not
the whole process" stance.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Protocol, Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel, Timestamp
from app.core.models.open_interest import OpenInterest
from app.flow.engine import FlowFeatureEngine
from app.market_data.exceptions import MarketDataError

logger = logging.getLogger(__name__)

DEFAULT_OPEN_INTEREST_POLL_INTERVAL_SECONDS = 60.0
"""Owner-approved V1 default (Stage 0A design review)."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TaskState(StrEnum):
    """Operational liveness of one Stage 0A-owned background task.

    Never a trading/data-quality signal - ``FlowSupervisorResult`` remains
    the sole analytical authority and ``FeatureQuality`` remains the sole
    data-quality authority (Stage 0A pre-commit review, blocking defect 2).
    This enum answers exactly one narrow question: is the task itself still
    executing.

    ``FAILED`` means the task's own coroutine ended with an exception other
    than ``asyncio.CancelledError`` - a genuine, unexpected termination.
    ``STOPPED`` covers both "never started" and "ended normally/via
    intentional cancellation" - intentional shutdown is never reported as
    ``FAILED`` (see ``classify_task``).
    """

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class TaskHealth:
    """Immutable operational snapshot of one background task.

    ``exception_type`` is populated only when ``state`` is ``FAILED``, and
    is deliberately just the exception's class name - never its message,
    args, or traceback, which could carry request details/payload content.
    """

    state: TaskState
    exception_type: str | None = None


def classify_task(task: "asyncio.Task[object]") -> TaskHealth:
    """The single, shared rule for turning one ``asyncio.Task`` into a
    ``TaskHealth`` - used identically by ``OpenInterestPoller`` and
    ``FlowRealtimeBootstrap`` so "running/stopped/failed" means exactly the
    same thing everywhere in Stage 0A.

    Calling ``task.exception()`` here is what actually retrieves the
    exception from an already-done task - the same call that prevents
    asyncio's own "Task exception was never retrieved" warning. This
    function is normally invoked from a task's own ``add_done_callback``,
    so retrieval happens as soon as the task ends, never only on-demand.
    """
    if not task.done():
        return TaskHealth(state=TaskState.RUNNING)
    if task.cancelled():
        return TaskHealth(state=TaskState.STOPPED)
    exc = task.exception()
    if exc is not None:
        return TaskHealth(state=TaskState.FAILED, exception_type=type(exc).__name__)
    return TaskHealth(state=TaskState.STOPPED)


class OpenInterestPollerConfig(DomainModel):
    """The one Stage 0A-owned tuning value: how often to poll open interest.

    Colocated here rather than under ``app/core/config`` deliberately: this
    is Stage 0A-local infrastructure cadence, not a cross-cutting trading/
    risk config contract like ``TradingCycleConfig``/``MT5RolloverPolicyConfig``
    - the smallest isolated addition the approved design calls for. No other
    Flow tuning parameter (windows, depth bands, buffer capacities) is
    exposed here - every one of those already has a reviewed default
    elsewhere and no operational reason to override it in V1.
    """

    poll_interval_seconds: Annotated[float, Field(gt=0)] = DEFAULT_OPEN_INTEREST_POLL_INTERVAL_SECONDS

    @model_validator(mode="after")
    def _validate_finite(self) -> Self:
        if not math.isfinite(self.poll_interval_seconds):
            raise ValueError("poll_interval_seconds must be finite")
        return self


class OpenInterestSource(Protocol):
    """The one REST capability this poller needs.

    Satisfied structurally by ``BinanceFuturesMarketDataProvider`` - never
    imported here at the type level - and equally by a hand-written fake in
    tests. Narrow on purpose, mirroring the LLM explanation layer's own
    provider-transport seam one architectural layer over.
    """

    def get_open_interest(self, symbol: str) -> OpenInterest: ...


class OpenInterestPoller:
    """Periodically polls REST open interest for one configured symbol and
    feeds each successfully observed ``OpenInterest`` into a shared
    ``FlowFeatureEngine``.

    Owns exactly this one responsibility: no trading decision, no Market
    Evaluation, no other Flow domain, no broker/tracking integration, no LLM
    explanation layer, no HTTP/bot delivery surface.
    """

    def __init__(
        self,
        *,
        symbol: str,
        provider: OpenInterestSource,
        engine: FlowFeatureEngine,
        config: OpenInterestPollerConfig | None = None,
        clock: Callable[[], Timestamp] | None = None,
    ) -> None:
        self._symbol = symbol
        self._provider = provider
        self._engine = engine
        self._config = config if config is not None else OpenInterestPollerConfig()
        self._clock = clock if clock is not None else _utc_now
        self._task: asyncio.Task[None] | None = None
        self._task_health: TaskHealth = TaskHealth(state=TaskState.STOPPED)
        self.last_attempt_at: Timestamp | None = None
        self.last_success_at: Timestamp | None = None

    def start(self) -> None:
        """Begin polling in the background (idempotent). Restartable: a
        prior FAILED/STOPPED state is replaced by a fresh RUNNING state for
        the new task - no automatic restart happens on its own, this only
        supports an explicit, caller-initiated restart."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            self._task_health = TaskHealth(state=TaskState.RUNNING)
            self._task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: "asyncio.Task[None]") -> None:
        self._task_health = classify_task(task)
        if self._task_health.state is TaskState.FAILED:
            logger.error(
                "open interest poller task for %s terminated unexpectedly: %s",
                self._symbol,
                self._task_health.exception_type,
            )

    async def stop(self) -> None:
        """Cancel the background poll loop (idempotent).

        Only cancels/awaits a task that is not already done: an already-
        FAILED task must not be re-awaited here (that would re-raise its
        exception out of ``stop()``) - its terminal state was already
        captured by ``_on_task_done`` the instant it happened. Bounded by a
        timeout so a slow in-flight REST call being cancelled at shutdown
        can never block shutdown indefinitely.
        """
        if self._task is not None:
            if not self._task.done():
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(self._task, timeout=5)
            self._task = None

    @property
    def task_health(self) -> TaskHealth:
        """Operational liveness of the poll loop itself - never a trading/
        data-quality signal. ``MarketDataError`` never appears here: it is
        a normal, handled poll outcome (see ``poll_once``), not a task
        failure."""
        return self._task_health

    async def poll_once(self) -> bool:
        """Fetch open interest once and, on success, record it.

        Returns ``True`` on a successfully recorded observation, ``False``
        on a caught, transient provider failure (``MarketDataError``) -
        never fabricates a substitute observation either way. The
        synchronous REST call is bridged via ``asyncio.to_thread`` so it
        never blocks the event loop; ``FlowFeatureEngine.record_open_interest``
        is always called back on the event-loop thread, after the awaited
        thread call returns - never itself passed into ``asyncio.to_thread``.
        Any exception other than ``MarketDataError`` is a programming error
        and is deliberately left to propagate, never swallowed here.
        """
        self.last_attempt_at = self._clock()
        try:
            observation = await asyncio.to_thread(self._provider.get_open_interest, self._symbol)
        except MarketDataError as exc:
            logger.warning("open interest poll for %s failed: %s: %s", self._symbol, type(exc).__name__, exc)
            return False
        self._engine.record_open_interest(observation)
        self.last_success_at = self._clock()
        return True

    async def _run(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self._config.poll_interval_seconds)


__all__ = [
    "DEFAULT_OPEN_INTEREST_POLL_INTERVAL_SECONDS",
    "OpenInterestPoller",
    "OpenInterestPollerConfig",
    "OpenInterestSource",
    "TaskHealth",
    "TaskState",
    "classify_task",
]
