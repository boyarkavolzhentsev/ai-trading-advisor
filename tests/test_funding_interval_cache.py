"""FundingIntervalCache: slow REST side-channel behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.exceptions import ProviderUnavailableError
from app.market_data.providers.binance.futures.realtime.funding_cache import FundingIntervalCache

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_is_stale_before_first_refresh() -> None:
    cache = FundingIntervalCache(fetch_all=lambda: _immediate({}), clock=lambda: NOW)
    assert cache.is_stale() is True
    assert cache.get("BTCUSDT") is None


@pytest.mark.asyncio
async def test_refresh_populates_cache_and_clears_staleness() -> None:
    clock = _MutableClock(NOW)
    cache = FundingIntervalCache(
        fetch_all=lambda: _immediate({"BTCUSDT": 4}), refresh_seconds=60, clock=clock
    )
    await cache.refresh_if_stale()

    assert cache.get("btcusdt") == 4
    assert cache.is_stale() is False


@pytest.mark.asyncio
async def test_refresh_is_skipped_when_not_stale() -> None:
    calls = []

    async def fetch_all() -> dict[str, int]:
        calls.append(1)
        return {"BTCUSDT": 4}

    clock = _MutableClock(NOW)
    cache = FundingIntervalCache(fetch_all=fetch_all, refresh_seconds=3600, clock=clock)
    await cache.refresh_if_stale()
    await cache.refresh_if_stale()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_refresh_becomes_due_again_after_refresh_seconds() -> None:
    clock = _MutableClock(NOW)
    cache = FundingIntervalCache(fetch_all=lambda: _immediate({}), refresh_seconds=10, clock=clock)
    await cache.refresh_if_stale()
    assert cache.is_stale() is False

    clock.advance(timedelta(seconds=11))
    assert cache.is_stale() is True


@pytest.mark.asyncio
async def test_failed_refresh_keeps_previous_cache_and_never_raises() -> None:
    clock = _MutableClock(NOW)
    cache = FundingIntervalCache(fetch_all=lambda: _immediate({"BTCUSDT": 4}), clock=clock)
    await cache.refresh_if_stale()

    clock.advance(timedelta(hours=2))

    async def failing_fetch() -> dict[str, int]:
        raise ProviderUnavailableError("network down")

    cache._fetch_all = failing_fetch  # noqa: SLF001 - swap the side-channel for this call
    await cache.refresh_if_stale()  # must not raise

    assert cache.get("BTCUSDT") == 4  # previous value preserved
    assert cache.is_stale() is False  # last_refresh was still updated


def test_unknown_symbol_returns_none_never_a_default() -> None:
    cache = FundingIntervalCache(fetch_all=lambda: _immediate({"BTCUSDT": 8}))
    assert cache.get("ETHUSDT") is None


class _MutableClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


async def _immediate(value: dict[str, int]) -> dict[str, int]:
    return value
