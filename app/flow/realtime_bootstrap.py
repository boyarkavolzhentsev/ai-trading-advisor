"""Stage 0A Flow production wiring: real Binance Futures realtime -> the
existing, unmodified ``FlowFeatureEngine`` -> the existing, unmodified six
Flow analysts -> the existing, unmodified ``FlowSupervisor`` ->
``FlowSupervisorResult``.

``FlowRealtimeBootstrap`` owns exactly one configured ``(symbol,
contract_type)`` pair's realtime lifecycle: constructing the existing
production transports/streams (``WebSocketTransport``,
``BinanceFuturesMarketStream``, ``BinanceFuturesOrderBookStream``,
``OrderBookSynchronizer`` via the stream, ``FundingIntervalCache``), feeding
every event they emit into ``FlowFeatureEngine`` unchanged, and exposing one
method that builds the current production ``FlowSupervisorResult`` from
whatever real history is retained. It owns no trading/decision logic of any
kind - no Market Evaluation, Strategy Router, Judge, Policy, Risk,
Portfolio, or Session dependency exists here, no broker/tracking
integration, no LLM explanation layer, and no HTTP/bot delivery surface of
any kind is reachable from here (enforced by
``tests/test_flow_realtime_bootstrap_module_hygiene.py``).

Never invokes the deterministic runtime-cycle orchestration boundary - this
is Flow realtime infrastructure only (Stage 0A). No second market-data representation is introduced: every
value fed to ``FlowFeatureEngine`` is the exact, unchanged model the
existing realtime/REST layer already produces (``TradeEvent``,
``LiquidationEvent``, ``OrderBookSnapshot``, ``FundingRate``,
``OpenInterest``).

Approved single-event-loop concurrency invariant (Stage 0A design review,
item 5): no lock guards ``FlowFeatureEngine`` here, and none is needed, as
long as ALL of the following remain true:

- exactly one process, one asyncio event loop (owner-mandated for V1: no
  worker process, no queue, no Redis);
- ``FlowFeatureEngine.record_*``/``build_snapshot`` remain plain synchronous,
  non-``async``, non-awaiting methods (true today - verified directly by
  ``tests/test_flow_realtime_bootstrap_concurrency.py``);
- engine mutation (every ``record_*`` call) and engine reads
  (``build_snapshot``) are never executed via ``asyncio.to_thread`` or any
  other thread.

Under CPython's GIL plus asyncio's cooperative scheduling, a coroutine is
only preempted at an ``await`` point; since none of the engine's methods
contains one, two calls from two different tasks can never interleave
mid-execution - each runs to completion as one indivisible step from the
event loop's perspective. Only the genuinely blocking REST calls (order-book
snapshot fetch, open-interest poll, funding-interval refresh) are bridged
via ``asyncio.to_thread`` - their results are always handed back to, and
applied on, the event-loop thread, never from inside the worker thread. If
any of the three conditions above ever changes, this reasoning must be
revisited before removing this comment.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import math
from collections.abc import Coroutine
from dataclasses import dataclass

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.stream_health import StreamHealth
from app.flow.engine import FlowFeatureEngine
from app.flow.open_interest_poller import (
    OpenInterestPoller,
    OpenInterestPollerConfig,
    OpenInterestSource,
    TaskHealth,
    TaskState,
    classify_task,
)
from app.flow_analysts.funding import FundingAnalyst
from app.flow_analysts.liquidation import LiquidationAnalyst
from app.flow_analysts.open_interest import OpenInterestAnalyst
from app.flow_analysts.order_book import OrderBookLiquidityAnalyst
from app.flow_analysts.price_flow_relationship import PriceFlowRelationshipAnalyst
from app.flow_analysts.protocols import FlowAnalyst
from app.flow_analysts.taker_flow import TakerFlowAnalyst
from app.flow_supervisor.supervisor import FlowSupervisor
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures.constants import BINANCE_FUTURES_BASE_URL, DEFAULT_TIMEOUT_SECONDS
from app.market_data.providers.binance.futures.provider import BinanceFuturesMarketDataProvider
from app.market_data.providers.binance.futures.realtime import (
    FundingIntervalCache,
    make_binance_fetch_all,
    make_market_transport,
    make_public_transport,
    make_snapshot_fetcher,
)
from app.market_data.providers.binance.futures.realtime.provider import (
    BinanceFuturesMarketStream,
    BinanceFuturesOrderBookStream,
    SnapshotFetcher,
)
from app.market_data.realtime.transport import WebSocketTransport

logger = logging.getLogger(__name__)

_FUNDING_CACHE_CHECK_INTERVAL_SECONDS = 60.0
"""Wake cadence of Stage 0A's own background loop that repeatedly calls
``FundingIntervalCache.refresh_if_stale()`` - a pure operational polling
detail, never a second refresh-cadence policy: whether a real network
refresh actually occurs on any given wake-up remains entirely governed by
the existing, unmodified cache's own ``refresh_seconds``/``is_stale()``
contract (``refresh_if_stale()`` is a cheap no-op whenever the cache is not
yet stale). This constant only decides how promptly this loop notices once
the cache's own policy says a refresh is due."""

_STARTUP_CHECKPOINT_SECONDS = 0.01
"""How long ``start()`` yields to the event loop after creating every
Stage 0A-owned background task, solely to give a task that fails
immediately (a programming bug, not a connectivity condition) a chance to
surface before ``start()`` returns. Deliberately small and fixed - this is
not a warm-up wait for market data (which can legitimately take minutes)
and never blocks on network I/O; it only catches a task whose own coroutine
raises essentially immediately."""


class FlowRealtimeBootstrapStartupError(RuntimeError):
    """Raised by ``start()`` when one or more Stage 0A-owned background
    tasks are already ``FAILED`` at the startup checkpoint - a genuine
    programming/infrastructure defect, never raised merely because a
    transport is still connecting/reconnecting (see
    ``app.flow.open_interest_poller.TaskState``)."""


_FLOW_ANALYSTS: tuple[FlowAnalyst, ...] = (
    TakerFlowAnalyst(),
    LiquidationAnalyst(),
    OrderBookLiquidityAnalyst(),
    OpenInterestAnalyst(),
    FundingAnalyst(),
    PriceFlowRelationshipAnalyst(),
)
"""All six Stage 2B specialists, zero-argument/stateless, in
``FlowSupervisor``'s own canonical ``DEFAULT_EXPECTED_ANALYSTS`` order. Every
one of the six is always invoked every call - abstention is a legitimate,
typed per-analyst result (``AnalystOutcome.ABSTAINED``), never represented
by omitting a call."""


class FlowRealtimeBootstrapConfig(DomainModel):
    """The minimal V1 deployment configuration for one Flow realtime
    bootstrap instance: which one ``(symbol, contract_type)`` pair it owns,
    plus the one open-interest polling cadence Stage 0A introduces. Every
    other Flow tuning parameter (analytics windows, depth bands, buffer
    capacities, reconnect/backoff policy) already has a reviewed default
    inside the existing, unmodified components this module wires together
    and is deliberately not re-exposed here.
    """

    symbol: Symbol
    contract_type: ContractType
    open_interest: OpenInterestPollerConfig = Field(default_factory=OpenInterestPollerConfig)


@dataclass(frozen=True, slots=True)
class FlowRealtimeBootstrapHealth:
    """Point-in-time composite operational snapshot.

    Never a trading-readiness verdict and never a duplicate of
    ``FeatureQuality``: the analytical state of Flow itself is
    ``FlowSupervisorResult.outcome`` from ``build_flow_result()``, not
    anything reported here. ``open_interest_last_success_at`` is ``None``
    only when no REST poll has yet succeeded (e.g. immediately after
    ``start()``) - never fabricated.

    ``market``/``order_book`` (``StreamHealth``) remain the sole authority
    on *connection* state - a task's own ``TaskState`` answers a narrower,
    independent question: is the Stage 0A runner/consumer coroutine itself
    still executing. The two are deliberately never merged: a transport
    task can be ``RUNNING`` while its ``StreamHealth.status`` is
    ``DISCONNECTED``/``RECONNECTING`` (the reconnect machinery is alive and
    working exactly as designed), and only a task whose own coroutine
    raised an unexpected exception is ever ``FAILED``.
    """

    market: StreamHealth
    order_book: StreamHealth
    open_interest_last_attempt_at: Timestamp | None
    open_interest_last_success_at: Timestamp | None
    market_transport_task: TaskHealth
    public_transport_task: TaskHealth
    trades_task: TaskHealth
    liquidations_task: TaskHealth
    order_book_task: TaskHealth
    funding_task: TaskHealth
    funding_cache_refresh_task: TaskHealth
    open_interest_task: TaskHealth


class FlowRealtimeBootstrap:
    """Owns the long-lived Binance Futures realtime connection lifecycle for
    exactly one configured ``(symbol, contract_type)``, feeding a shared
    ``FlowFeatureEngine``.

    Every dependency is injectable for testing (no real network, no real
    REST client construction) - each defaults to the real production
    component when omitted. No global singleton; no hidden wall-clock read
    anywhere in this class (``build_flow_result`` takes ``as_of`` explicitly).
    """

    def __init__(
        self,
        *,
        config: FlowRealtimeBootstrapConfig,
        engine: FlowFeatureEngine | None = None,
        market_transport: WebSocketTransport | None = None,
        public_transport: WebSocketTransport | None = None,
        rest_client: BinanceRestClient | None = None,
        open_interest_provider: OpenInterestSource | None = None,
        snapshot_fetcher: SnapshotFetcher | None = None,
        funding_interval_cache: FundingIntervalCache | None = None,
        funding_cache_check_interval_seconds: float = _FUNDING_CACHE_CHECK_INTERVAL_SECONDS,
    ) -> None:
        if not math.isfinite(funding_cache_check_interval_seconds) or funding_cache_check_interval_seconds <= 0:
            raise ValueError(
                "funding_cache_check_interval_seconds must be finite and > 0, "
                f"got {funding_cache_check_interval_seconds!r}"
            )
        self._config = config
        self._engine = engine if engine is not None else FlowFeatureEngine()
        self._funding_cache_check_interval_seconds = funding_cache_check_interval_seconds

        self._rest_client: BinanceRestClient | None = rest_client
        self._owns_rest_client = rest_client is None
        needs_default_rest_client = rest_client is None and (
            open_interest_provider is None or snapshot_fetcher is None or funding_interval_cache is None
        )
        default_provider: BinanceFuturesMarketDataProvider | None = None
        if needs_default_rest_client:
            if self._rest_client is None:
                self._rest_client = BinanceRestClient(base_url=BINANCE_FUTURES_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
            default_provider = BinanceFuturesMarketDataProvider(self._rest_client)

        self._open_interest_provider: OpenInterestSource = (
            open_interest_provider if open_interest_provider is not None else default_provider  # type: ignore[assignment]
        )
        self._snapshot_fetcher: SnapshotFetcher = (
            snapshot_fetcher if snapshot_fetcher is not None else make_snapshot_fetcher(default_provider)  # type: ignore[arg-type]
        )
        self._funding_interval_cache = (
            funding_interval_cache
            if funding_interval_cache is not None
            else FundingIntervalCache(make_binance_fetch_all(self._rest_client))  # type: ignore[arg-type]
        )

        self._market_transport = market_transport if market_transport is not None else make_market_transport()
        self._public_transport = public_transport if public_transport is not None else make_public_transport()

        self._market_stream = BinanceFuturesMarketStream(
            self._market_transport, funding_interval_cache=self._funding_interval_cache
        )
        self._order_book_stream = BinanceFuturesOrderBookStream(
            self._public_transport, snapshot_fetcher=self._snapshot_fetcher
        )
        self._oi_poller = OpenInterestPoller(
            symbol=config.symbol,
            provider=self._open_interest_provider,
            engine=self._engine,
            config=config.open_interest,
        )
        self._supervisor = FlowSupervisor()

        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._task_health: dict[str, TaskHealth] = {}
        self._started = False

    # --- named-task bookkeeping (shared by every Stage 0A-owned task) ---

    def _start_task(self, name: str, coro: Coroutine[object, object, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks[name] = task
        self._task_health[name] = TaskHealth(state=TaskState.RUNNING)
        task.add_done_callback(functools.partial(self._on_task_done, name))

    def _on_task_done(self, name: str, task: "asyncio.Task[None]") -> None:
        health = classify_task(task)
        self._task_health[name] = health
        if health.state is TaskState.FAILED:
            logger.error("Stage 0A task %r terminated unexpectedly: %s", name, health.exception_type)

    def _task_state_of(self, name: str) -> TaskHealth:
        return self._task_health.get(name, TaskHealth(state=TaskState.STOPPED))

    # --- lifecycle ---------------------------------------------------

    async def start(self) -> None:
        """Idempotent. Starts the existing transports/streams, begins
        forwarding every capability into ``FlowFeatureEngine``, starts
        open-interest polling, and starts the funding-interval-cache
        refresh loop. Never waits for analytical warm-up and never fails
        merely because the first market event has not arrived yet -
        readiness is answered by calling ``build_flow_result`` itself.

        After creating every task, yields briefly (see
        ``_STARTUP_CHECKPOINT_SECONDS``) so a task that fails essentially
        immediately (a programming bug) is caught here rather than
        silently disappearing: on such a failure, everything already
        started is torn down via ``stop()`` and
        ``FlowRealtimeBootstrapStartupError`` is raised. A task that is
        merely still connecting/reconnecting is never treated as failed.
        """
        if self._started:
            return
        self._started = True

        self._start_task("market_transport", self._market_transport.run())
        self._start_task("public_transport", self._public_transport.run())
        self._market_stream.start()
        self._order_book_stream.start()
        self._start_task("trades", self._forward_trades())
        self._start_task("liquidations", self._forward_liquidations())
        self._start_task("order_book", self._forward_order_book())
        self._start_task("funding", self._forward_funding())
        self._start_task("funding_cache_refresh", self._run_funding_cache_refresh())
        self._oi_poller.start()

        await asyncio.sleep(_STARTUP_CHECKPOINT_SECONDS)

        failed = sorted(name for name, health in self._task_health.items() if health.state is TaskState.FAILED)
        if self._oi_poller.task_health.state is TaskState.FAILED:
            failed.append("open_interest_poller")
        if failed:
            await self.stop()
            raise FlowRealtimeBootstrapStartupError(
                f"Stage 0A background task(s) failed during startup: {failed}"
            )

    async def stop(self) -> None:
        """Idempotent. Reverses ``start()`` in dependency order: external
        forwarding consumers and the funding-cache refresh loop first, then
        the streams' own internal dispatch loops, then the raw transports,
        then (only if this instance constructed it) the REST client. Never
        closes a caller-injected resource.

        Only cancels/awaits a task that is not already done: an
        already-FAILED task must never be re-awaited here (that would
        re-raise its exception out of ``stop()``) - its terminal state was
        already captured by ``_on_task_done`` the instant it happened.
        """
        if not self._started:
            return
        self._started = False

        await self._oi_poller.stop()

        consumer_task_names = ("trades", "liquidations", "order_book", "funding", "funding_cache_refresh")
        for name in consumer_task_names:
            task = self._tasks.get(name)
            if task is not None and not task.done():
                task.cancel()
        for name in consumer_task_names:
            task = self._tasks.get(name)
            if task is not None and not task.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        await self._market_stream.stop()
        await self._order_book_stream.stop()

        await self._market_transport.stop()
        await self._public_transport.stop()
        for name in ("market_transport", "public_transport"):
            task = self._tasks.get(name)
            if task is not None and not task.done():
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(task, timeout=5)

        self._tasks = {}

        if self._owns_rest_client and self._rest_client is not None:
            self._rest_client.close()

    # --- forwarding: existing async iterators -> existing FlowFeatureEngine ---

    async def _forward_trades(self) -> None:
        async for trade in self._market_stream.trades(self._config.symbol):
            self._engine.record_trade(trade)

    async def _forward_liquidations(self) -> None:
        """Subscribes to the per-symbol liquidation stream (never the
        all-market stream) for the one configured symbol, and defensively
        re-checks the authoritative event symbol before recording - never
        records another symbol's liquidation into this engine, regardless
        of which stream form the underlying provider happens to use."""
        symbol = self._config.symbol.upper()
        async for event in self._market_stream.liquidations(symbol):
            if event.symbol != symbol:
                continue
            self._engine.record_liquidation(event)

    async def _forward_order_book(self) -> None:
        async for snapshot in self._order_book_stream.order_book(self._config.symbol):
            self._engine.record_order_book(snapshot)

    async def _forward_funding(self) -> None:
        async for funding in self._market_stream.mark_price(self._config.symbol):
            self._engine.record_funding(funding)

    async def _run_funding_cache_refresh(self) -> None:
        """Repeatedly gives the existing, unmodified ``FundingIntervalCache``
        a chance to refresh itself via its own public ``refresh_if_stale()``
        contract - the fix for the pre-commit review's funding-cache
        defect. The very first iteration (as soon as this task gets its
        first turn on the event loop, effectively at bootstrap startup)
        performs the initial best-effort refresh; the loop then continues
        for the process lifetime.

        This function never decides whether a network call actually
        happens - ``refresh_if_stale()`` itself is a cheap no-op whenever
        ``is_stale()`` is false, so ``_funding_cache_check_interval_seconds``
        is only a wake-up cadence, never a competing refresh policy (its
        constructor default, ``_FUNDING_CACHE_CHECK_INTERVAL_SECONDS``, is
        the only production value; it is otherwise injectable purely so
        tests can observe multiple wake-ups without a real multi-minute
        wait - the cache's own ``refresh_seconds`` remains the sole
        authority over whether a wake-up actually triggers network I/O). A
        failed refresh is already handled entirely inside the existing
        cache (best-effort, keeps the previous value, never raises) - this
        loop never needs its own try/except for that. An unexpected
        exception here is a genuine bug and is left to propagate, ending
        only this task (visible via ``health().funding_cache_refresh_task``).
        """
        while True:
            await self._funding_interval_cache.refresh_if_stale()
            await asyncio.sleep(self._funding_cache_check_interval_seconds)

    def funding_interval_hours(self) -> int | None:
        """The configured symbol's currently cached funding-interval-hours
        fact, exactly as ``FundingIntervalCache.get()`` reports it - never
        fabricated, ``None`` until the first successful refresh. Exposed
        for operational inspection (e.g. the manual live-check script);
        every ``FundingRate`` this bootstrap records already carries the
        same fact via the existing mapper, independent of this accessor.
        """
        return self._funding_interval_cache.get(self._config.symbol)

    # --- production Flow result --------------------------------------

    def build_flow_result(self, *, as_of: Timestamp) -> FlowSupervisorResult:
        """Build the current production ``FlowSupervisorResult`` from
        whatever real history is currently retained.

        May legitimately return ``ANALYZED``, ``PARTIAL``, or
        ``INSUFFICIENT_EVIDENCE`` depending on real observations retained so
        far - this is always allowed to be called, immediately after
        ``start()`` included; it never waits for an arbitrary warm-up timer
        and never fabricates a neutral/zero fact. All six analysts are
        always invoked, in ``FlowSupervisor``'s own canonical order; a
        quiet/insufficient domain abstains (``AnalystOutcome.ABSTAINED``) -
        it is never simply omitted from the six.
        """
        snapshot = self._engine.build_snapshot(
            symbol=self._config.symbol,
            contract_type=self._config.contract_type,
            observation_time=as_of,
        )
        results = tuple(analyst.analyze(snapshot) for analyst in _FLOW_ANALYSTS)
        return self._supervisor.aggregate(results)

    # --- health --------------------------------------------------------

    def health(self) -> FlowRealtimeBootstrapHealth:
        """Cheap, synchronous, point-in-time operational health only - never
        a trading-readiness signal (see ``build_flow_result``)."""
        return FlowRealtimeBootstrapHealth(
            market=self._market_stream.health(),
            order_book=self._order_book_stream.health(),
            open_interest_last_attempt_at=self._oi_poller.last_attempt_at,
            open_interest_last_success_at=self._oi_poller.last_success_at,
            market_transport_task=self._task_state_of("market_transport"),
            public_transport_task=self._task_state_of("public_transport"),
            trades_task=self._task_state_of("trades"),
            liquidations_task=self._task_state_of("liquidations"),
            order_book_task=self._task_state_of("order_book"),
            funding_task=self._task_state_of("funding"),
            funding_cache_refresh_task=self._task_state_of("funding_cache_refresh"),
            open_interest_task=self._oi_poller.task_health,
        )


__all__ = [
    "FlowRealtimeBootstrap",
    "FlowRealtimeBootstrapConfig",
    "FlowRealtimeBootstrapHealth",
    "FlowRealtimeBootstrapStartupError",
]
