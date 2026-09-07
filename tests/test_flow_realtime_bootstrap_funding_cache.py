"""Stage 0A pre-commit review correction: FundingIntervalCache lifecycle
tests (blocking defect 1).

Every test here constructs the REAL, unmodified ``FundingIntervalCache``
(``app.market_data.providers.binance.futures.realtime.funding_cache``) with
a fake ``fetch_all`` callable - never a duck-typed stand-in for the cache
itself - so these tests exercise the cache's own existing
``refresh_seconds``/``is_stale()``/``refresh_if_stale()`` contract for
real, proving Stage 0A's background refresh loop actually drives it
correctly. No real Binance access anywhere.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums.instrument import ContractType
from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig
from app.market_data.exceptions import MarketDataError
from app.market_data.providers.binance.futures.realtime.funding_cache import FundingIntervalCache
from tests.flow_realtime_bootstrap_support import NOW, SYMBOL, make_bootstrap, millis


def _millis(dt) -> int:
    return millis(dt)


class _CountingFetchAll:
    """Fake ``FetchAllFn``: records every call, returns a fixed mapping."""

    def __init__(self, *, interval_hours: int = 8) -> None:
        self.calls = 0
        self._interval_hours = interval_hours

    async def __call__(self) -> dict[str, int]:
        self.calls += 1
        return {SYMBOL: self._interval_hours}


class _AlwaysFailingFetchAll:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> dict[str, int]:
        self.calls += 1
        raise MarketDataError("simulated funding-info fetch failure")


class _SucceedsOnceThenFailsFetchAll:
    """First call succeeds with a real interval; every subsequent call
    fails - proves a transient later failure never erases the previously
    cached valid value (the existing cache's own best-effort semantics)."""

    def __init__(self, *, interval_hours: int = 8) -> None:
        self.calls = 0
        self._interval_hours = interval_hours

    async def __call__(self) -> dict[str, int]:
        self.calls += 1
        if self.calls == 1:
            return {SYMBOL: self._interval_hours}
        raise MarketDataError("simulated transient failure after initial success")


@pytest.mark.asyncio
async def test_bootstrap_startup_causes_refresh_if_stale_to_run() -> None:
    fetch_all = _CountingFetchAll()
    cache = FundingIntervalCache(fetch_all, refresh_seconds=3600.0)
    bootstrap, _, _ = make_bootstrap(funding_interval_cache=cache)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    try:
        assert fetch_all.calls >= 1
        assert cache.get(SYMBOL) == 8
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_successful_refresh_populates_interval_used_by_funding_rate_mapping() -> None:
    fetch_all = _CountingFetchAll(interval_hours=8)
    cache = FundingIntervalCache(fetch_all, refresh_seconds=3600.0)
    bootstrap, market_connection, _ = make_bootstrap(funding_interval_cache=cache)

    await bootstrap.start()
    await asyncio.sleep(0.02)  # let the initial refresh land before the mark-price event

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@markPrice@1s",
        {"e": "markPriceUpdate", "E": _millis(NOW), "s": SYMBOL, "p": "64010.00", "P": "64000.00", "i": "64005.00", "r": "0.0001"},
    )
    await asyncio.sleep(0.05)

    try:
        from app.core.enums.instrument import ContractType

        retained = bootstrap._engine.history_for(SYMBOL, ContractType.PERPETUAL).funding.latest()
        assert len(retained) == 1
        assert retained[0].funding_interval_hours == 8
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_temporary_refresh_failure_does_not_fabricate_interval() -> None:
    fetch_all = _AlwaysFailingFetchAll()
    cache = FundingIntervalCache(fetch_all, refresh_seconds=3600.0)
    bootstrap, _, _ = make_bootstrap(funding_interval_cache=cache)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    try:
        assert fetch_all.calls >= 1
        assert cache.get(SYMBOL) is None  # never fabricated
        # bootstrap itself must stay healthy - a refresh failure is not a task failure
        from app.flow.open_interest_poller import TaskState

        assert bootstrap.health().funding_cache_refresh_task.state is TaskState.RUNNING
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_temporary_refresh_failure_does_not_stop_funding_rate_forwarding() -> None:
    fetch_all = _AlwaysFailingFetchAll()
    cache = FundingIntervalCache(fetch_all, refresh_seconds=3600.0)
    bootstrap, market_connection, _ = make_bootstrap(funding_interval_cache=cache)

    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@markPrice@1s",
        {"e": "markPriceUpdate", "E": _millis(NOW), "s": SYMBOL, "p": "64010.00", "P": "64000.00", "i": "64005.00", "r": "0.0001"},
    )
    await asyncio.sleep(0.05)

    try:
        from app.core.enums.instrument import ContractType

        retained = bootstrap._engine.history_for(SYMBOL, ContractType.PERPETUAL).funding.latest()
        assert len(retained) == 1
        assert retained[0].funding_interval_hours is None  # legitimately unknown, never fabricated
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_previously_cached_valid_interval_survives_later_transient_failure() -> None:
    fetch_all = _SucceedsOnceThenFailsFetchAll(interval_hours=8)
    # short refresh_seconds so a second (failing) refresh attempt happens quickly;
    # short check-interval (test-only seam - never a second refresh-cadence
    # policy, see FlowRealtimeBootstrap's own docstring) so the wake-up loop
    # actually notices without a real multi-minute wait.
    cache = FundingIntervalCache(fetch_all, refresh_seconds=0.05)
    bootstrap, _, _ = make_bootstrap(funding_interval_cache=cache, funding_cache_check_interval_seconds=0.03)

    await bootstrap.start()
    await asyncio.sleep(0.02)
    assert cache.get(SYMBOL) == 8  # first call succeeded

    # let several wake-ups pass, well past refresh_seconds - the (failing) second call happens
    await asyncio.sleep(0.15)
    try:
        assert fetch_all.calls >= 2
        assert cache.get(SYMBOL) == 8  # still the last real, valid value - never erased
    finally:
        await bootstrap.stop()


@pytest.mark.asyncio
async def test_refresh_continues_over_process_lifetime_per_existing_cache_policy() -> None:
    fetch_all = _CountingFetchAll(interval_hours=8)
    cache = FundingIntervalCache(fetch_all, refresh_seconds=0.05)
    bootstrap, _, _ = make_bootstrap(funding_interval_cache=cache, funding_cache_check_interval_seconds=0.03)

    await bootstrap.start()
    await asyncio.sleep(0.2)
    try:
        # multiple refreshes occurred, gated by the cache's OWN refresh_seconds
        # (0.05s) - never by Stage 0A inventing its own competing cadence
        assert fetch_all.calls >= 2
    finally:
        await bootstrap.stop()


def test_no_hardcoded_funding_interval_exists_in_bootstrap_source() -> None:
    """AST-scan: realtime_bootstrap.py never passes ``funding_interval_hours``
    as a keyword argument anywhere in its own source at all - the only path
    to that field is the existing FundingIntervalCache/mapper pipeline,
    which this module never bypasses."""
    import app.flow.realtime_bootstrap as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    offending = [node for node in ast.walk(tree) if isinstance(node, ast.keyword) and node.arg == "funding_interval_hours"]
    assert offending == [], "realtime_bootstrap.py must never itself set funding_interval_hours"


# --------------------------------------------------------------------------- #
# funding_cache_check_interval_seconds validation (Stage 0A micro-correction,
# blocking finding A). Purely a constructor-validation concern - no
# transport/REST-client/network resource is ever started by these tests:
# invalid values are rejected as the very first statement in __init__,
# before any such object is constructed; valid values are exercised through
# the existing fully fake-backed make_bootstrap() helper.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_value", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_invalid_funding_cache_check_interval_rejected(bad_value: float) -> None:
    config = FlowRealtimeBootstrapConfig(symbol=SYMBOL, contract_type=ContractType.PERPETUAL)
    with pytest.raises(ValueError, match="funding_cache_check_interval_seconds"):
        FlowRealtimeBootstrap(config=config, funding_cache_check_interval_seconds=bad_value)


@pytest.mark.parametrize("good_value", [60.0, 0.001, 5.0])
def test_valid_funding_cache_check_interval_accepted(good_value: float) -> None:
    bootstrap, _, _ = make_bootstrap(funding_cache_check_interval_seconds=good_value)
    assert bootstrap._funding_cache_check_interval_seconds == good_value
