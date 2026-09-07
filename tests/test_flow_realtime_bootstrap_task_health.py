"""Stage 0A pre-commit review correction: background-task-health tests
(blocking defect 2).

Covers: healthy tasks report RUNNING; an unexpected exception in one task
marks only that task FAILED while independent tasks stay RUNNING; a
MarketDataError in the OI poller never becomes a task failure; a failed
task's exception is retrieved (no "Task exception was never retrieved"
diagnostic - see the module-level note above
``test_failed_task_exception_is_retrieved_without_asyncio_warning`` for why
this is observed via ``caplog`` against the ``asyncio`` logger, never via
``warnings``); a normal stop() reports STOPPED, never FAILED; an immediate
startup failure is detected and cleaned up by start(); a disconnected
transport is distinguishable from a failed transport-runner task. No real
Binance access anywhere.
"""

from __future__ import annotations

import asyncio
import gc
import logging

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.stream import StreamStatus
from app.flow.engine import FlowFeatureEngine
from app.flow.open_interest_poller import OpenInterestPoller, OpenInterestPollerConfig, TaskState
from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig, FlowRealtimeBootstrapStartupError
from app.market_data.exceptions import MarketDataError
from app.market_data.realtime.transport import WebSocketTransport
from tests.flow_realtime_bootstrap_support import (
    NOW,
    SYMBOL,
    FailingOpenInterestSource,
    FakeConnection,
    FakeOpenInterestSource,
    make_bootstrap,
    millis,
    subscribe_message,
)


def _millis(dt) -> int:
    return millis(dt)


class _BrokenEngine:
    """Records everything normally, but raises on record_trade specifically -
    used to force one, and only one, forwarding task to fail from a real
    call path, without touching any production file."""

    def __init__(self, *, real_engine: FlowFeatureEngine) -> None:
        self._real = real_engine
        self.trade_calls = 0

    def record_trade(self, trade) -> None:
        self.trade_calls += 1
        raise ValueError("simulated programming bug in trade handling")

    def record_liquidation(self, event) -> None:
        self._real.record_liquidation(event)

    def record_order_book(self, snapshot) -> None:
        self._real.record_order_book(snapshot)

    def record_open_interest(self, observation) -> None:
        self._real.record_open_interest(observation)

    def record_funding(self, observation) -> None:
        self._real.record_funding(observation)

    def build_snapshot(self, **kwargs):
        return self._real.build_snapshot(**kwargs)

    def history_for(self, *args, **kwargs):
        return self._real.history_for(*args, **kwargs)


# --------------------------------------------------------------------------- #
# 1. healthy forwarding tasks report RUNNING
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_healthy_tasks_report_running() -> None:
    bootstrap, _, _ = make_bootstrap()
    await bootstrap.start()
    try:
        health = bootstrap.health()
        assert health.market_transport_task.state is TaskState.RUNNING
        assert health.public_transport_task.state is TaskState.RUNNING
        assert health.trades_task.state is TaskState.RUNNING
        assert health.liquidations_task.state is TaskState.RUNNING
        assert health.order_book_task.state is TaskState.RUNNING
        assert health.funding_task.state is TaskState.RUNNING
        assert health.funding_cache_refresh_task.state is TaskState.RUNNING
        assert health.open_interest_task.state is TaskState.RUNNING
    finally:
        await bootstrap.stop()


# --------------------------------------------------------------------------- #
# 2 & 3. unexpected trade-forwarding exception -> trade task FAILED,
#         funding task remains independent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unexpected_trade_forwarding_exception_marks_only_trade_task_failed() -> None:
    real_engine = FlowFeatureEngine()
    broken_engine = _BrokenEngine(real_engine=real_engine)
    bootstrap, market_connection, _ = make_bootstrap(engine=broken_engine)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@aggTrade",
        {"e": "aggTrade", "E": _millis(NOW), "s": SYMBOL, "a": 1, "p": "64000.00", "q": "0.1", "f": 1, "l": 1, "T": _millis(NOW), "m": False},
    )
    await asyncio.sleep(0.05)

    try:
        health = bootstrap.health()
        assert health.trades_task.state is TaskState.FAILED
        assert health.trades_task.exception_type == "ValueError"
        # funding forwarding is a completely independent task/coroutine and
        # must not be affected by the trade task's own failure
        assert health.funding_task.state is TaskState.RUNNING
        assert health.liquidations_task.state is TaskState.RUNNING
        assert health.order_book_task.state is TaskState.RUNNING
    finally:
        await bootstrap.stop()


# --------------------------------------------------------------------------- #
# 4 & 5. OI: unexpected programming error -> FAILED; MarketDataError -> RUNNING
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_oi_unexpected_programming_error_marks_poller_task_failed() -> None:
    class BrokenSource:
        def get_open_interest(self, symbol: str):
            raise ZeroDivisionError("simulated programming bug")

    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=BrokenSource(), engine=engine, config=OpenInterestPollerConfig(poll_interval_seconds=60.0))
    poller.start()
    await asyncio.sleep(0.05)

    assert poller.task_health.state is TaskState.FAILED
    assert poller.task_health.exception_type == "ZeroDivisionError"

    # A FAILED task must remain inspectable as FAILED through stop() - it is
    # not silently reclassified as STOPPED merely because stop() was called
    # on an already-dead task (cancelling/awaiting an already-done task is a
    # no-op; the terminal state captured at the moment of failure persists
    # until the next explicit start()).
    await poller.stop()
    assert poller.task_health.state is TaskState.FAILED
    assert poller.task_health.exception_type == "ZeroDivisionError"


@pytest.mark.asyncio
async def test_oi_market_data_error_keeps_poller_task_running() -> None:
    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(
        symbol=SYMBOL, provider=FailingOpenInterestSource(), engine=engine,
        config=OpenInterestPollerConfig(poll_interval_seconds=60.0),
    )
    poller.start()
    await asyncio.sleep(0.05)

    assert poller.task_health.state is TaskState.RUNNING
    assert poller.last_attempt_at is not None
    assert poller.last_success_at is None

    await poller.stop()


# --------------------------------------------------------------------------- #
# 6. failed task exception is retrieved/observable - no asyncio
#    "Task exception was never retrieved" diagnostic.
#
# That diagnostic is emitted by asyncio's own default exception handler
# through the "asyncio" *logger* (logging.getLogger("asyncio").error(...)),
# never through Python's `warnings` module - mechanically confirmed during
# the Stage 0A final re-review with a standalone reproduction (a task with
# no done-callback attached, garbage collected without ever having its
# exception retrieved, logs the diagnostic via `logging`; `warnings.
# catch_warnings()` observes nothing regardless). This test therefore uses
# pytest's `caplog` against that exact logger, never `warnings`.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_failed_task_exception_is_retrieved_without_asyncio_warning(caplog) -> None:
    """Non-vacuous by construction: this test never calls
    ``task.exception()``/``.result()`` itself (that alone would retrieve the
    exception and mask the very thing being tested) and never mutates
    ``TaskHealth`` directly. The only way ``poller.task_health.state`` can
    already be ``FAILED`` below is through the real
    ``OpenInterestPoller._on_task_done`` -> ``classify_task`` path, which
    itself calls ``task.exception()`` - the same call that marks the
    exception retrieved in asyncio's own internal bookkeeping for that task
    object. If a future change ever stopped that call from happening, the
    task object would still carry an unretrieved exception when every
    reference to it is dropped and it is garbage collected below, and
    asyncio's default exception handler would then log the "never
    retrieved" diagnostic through the very ``asyncio`` logger this test
    observes via ``caplog`` - making this test fail for exactly that
    regression.
    """

    class BrokenSource:
        def get_open_interest(self, symbol: str):
            raise RuntimeError("simulated bug")

    caplog.set_level(logging.ERROR, logger="asyncio")

    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=BrokenSource(), engine=engine)
    poller.start()
    await asyncio.sleep(0.05)

    assert poller.task_health.state is TaskState.FAILED
    assert poller.task_health.exception_type == "RuntimeError"

    # Drop every reference to the task and force collection - exactly the
    # condition that triggers asyncio's own "never retrieved" diagnostic
    # when (and only when) the exception was never actually retrieved.
    task = poller._task
    del poller
    del task
    gc.collect()
    # Give the event loop several opportunities to run any scheduled
    # exception-handler callback before asserting silence.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    never_retrieved = [record for record in caplog.records if "never retrieved" in record.getMessage().lower()]
    assert never_retrieved == [], f"asyncio logged an unretrieved-exception diagnostic: {never_retrieved}"


# --------------------------------------------------------------------------- #
# 7. normal stop() -> STOPPED, not FAILED
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_normal_stop_reports_stopped_not_failed() -> None:
    bootstrap, _, _ = make_bootstrap()
    await bootstrap.start()
    await asyncio.sleep(0.02)
    await bootstrap.stop()

    # after stop(), self._tasks is cleared, so query the OI poller directly
    # (it retains its own task_health independent of the bootstrap's dict)
    assert bootstrap._oi_poller.task_health.state is TaskState.STOPPED


@pytest.mark.asyncio
async def test_oi_poller_stop_reports_stopped_not_failed() -> None:
    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=FakeOpenInterestSource(), engine=engine)
    poller.start()
    await asyncio.sleep(0.01)
    await poller.stop()
    assert poller.task_health.state is TaskState.STOPPED


@pytest.mark.asyncio
async def test_oi_poller_start_stop_start_resumes_polling() -> None:
    """Optional non-blocking improvement: a clean stop() followed by a
    fresh start() must resume polling with a new RUNNING task, not remain
    stuck in whatever terminal state the previous task left behind."""
    engine = FlowFeatureEngine()
    source = FakeOpenInterestSource()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=source, engine=engine, config=OpenInterestPollerConfig(poll_interval_seconds=60.0))

    poller.start()
    await asyncio.sleep(0.02)
    assert poller.task_health.state is TaskState.RUNNING
    first_calls = len(source.calls)
    assert first_calls >= 1

    await poller.stop()
    assert poller.task_health.state is TaskState.STOPPED

    poller.start()
    await asyncio.sleep(0.02)
    try:
        assert poller.task_health.state is TaskState.RUNNING
        assert len(source.calls) > first_calls  # a fresh poll actually happened
    finally:
        await poller.stop()


# --------------------------------------------------------------------------- #
# 8 & 9. immediate startup task failure is detected by start() and cleaned up
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_immediate_startup_task_failure_raises_and_cleans_up() -> None:
    """A market_transport whose connect() raises an exception NOT in
    connection_errors fails the transport task essentially immediately
    (pure in-process, no thread hop) - start() must detect this at its
    checkpoint, tear down whatever else it started, and raise."""

    async def _connect_raises_immediately() -> None:
        raise ValueError("simulated immediate programming bug, not a connectivity error")

    market_transport = WebSocketTransport(_connect_raises_immediately, build_subscribe_message=subscribe_message)
    bootstrap, _, _ = make_bootstrap(market_transport=market_transport)

    with pytest.raises(FlowRealtimeBootstrapStartupError, match="market_transport"):
        await bootstrap.start()

    # cleanup: bootstrap must not be left half-started
    assert bootstrap._started is False
    assert bootstrap._tasks == {}


@pytest.mark.asyncio
async def test_immediate_startup_failure_does_not_leave_other_tasks_running() -> None:
    async def _connect_raises_immediately() -> None:
        raise ValueError("simulated immediate programming bug")

    market_transport = WebSocketTransport(_connect_raises_immediately, build_subscribe_message=subscribe_message)
    bootstrap, _, _ = make_bootstrap(market_transport=market_transport)

    with pytest.raises(FlowRealtimeBootstrapStartupError):
        await bootstrap.start()

    # the public transport (and everything else) must have been stopped too,
    # not left dangling just because one specific task failed
    assert bootstrap.health().public_transport_task.state is TaskState.STOPPED


# --------------------------------------------------------------------------- #
# 10. connection DISCONNECTED while transport task RUNNING is distinguishable
#     from transport task FAILED
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_transport_runner_failure_after_successful_start_is_visible_via_health() -> None:
    """A transport task that fails well AFTER start() already returned
    successfully (not at the startup checkpoint) must still surface as
    FAILED through health() - the checkpoint only catches immediate
    failures; ongoing operation is covered by health() for the rest of the
    task's life. The connection is made to drop (as a real socket would),
    forcing WebSocketTransport.run()'s own reconnect attempt to hit a
    non-connectivity exception."""
    first_connection = FakeConnection()
    attempts = {"count": 0}

    async def connect() -> FakeConnection:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return first_connection
        raise ValueError("simulated late programming bug, not a connectivity error")

    market_transport = WebSocketTransport(connect, build_subscribe_message=subscribe_message)
    bootstrap, _, _ = make_bootstrap(market_transport=market_transport)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    assert bootstrap.health().market_transport_task.state is TaskState.RUNNING
    assert attempts["count"] == 1

    await first_connection.close()  # simulate a dropped connection
    await asyncio.sleep(0.02)  # run() reconnects -> attempt 2 -> ValueError -> task ends

    try:
        health = bootstrap.health()
        assert attempts["count"] == 2
        assert health.market_transport_task.state is TaskState.FAILED
        assert health.market_transport_task.exception_type == "ValueError"
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_disconnected_transport_is_not_a_failed_task() -> None:
    """OSError from connect() is a handled connectivity condition (retried
    with backoff internally by WebSocketTransport.run()) - the task itself
    stays RUNNING even though StreamHealth reports it disconnected."""

    async def _connect_refuses() -> None:
        raise OSError("connection refused")

    public_transport = WebSocketTransport(_connect_refuses, build_subscribe_message=subscribe_message)
    bootstrap, _, _ = make_bootstrap(public_transport=public_transport)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    try:
        health = bootstrap.health()
        assert health.public_transport_task.state is TaskState.RUNNING
        assert health.order_book.status is not StreamStatus.CONNECTED
    finally:
        await bootstrap.stop()
