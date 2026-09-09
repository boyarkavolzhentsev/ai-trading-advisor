"""``ProductionAdvisoryCycleLock`` tests (Stage 0D Production Advisory
Composition)."""

from __future__ import annotations

import asyncio

import pytest

from app.production_advisory.lock import ProductionAdvisoryCycleLock


@pytest.mark.asyncio
async def test_lock_starts_unlocked() -> None:
    lock = ProductionAdvisoryCycleLock()
    assert lock.locked is False


@pytest.mark.asyncio
async def test_lock_held_inside_context() -> None:
    lock = ProductionAdvisoryCycleLock()
    async with lock:
        assert lock.locked is True
    assert lock.locked is False


@pytest.mark.asyncio
async def test_lock_releases_on_exception() -> None:
    lock = ProductionAdvisoryCycleLock()
    with pytest.raises(ValueError):
        async with lock:
            raise ValueError("boom")
    assert lock.locked is False


@pytest.mark.asyncio
async def test_only_one_holder_at_a_time() -> None:
    lock = ProductionAdvisoryCycleLock()
    order: list[str] = []

    async def holder(name: str) -> None:
        async with lock:
            order.append(f"{name}-enter")
            await asyncio.sleep(0.01)
            order.append(f"{name}-exit")

    await asyncio.gather(holder("a"), holder("b"))

    # one holder's enter/exit must be fully contiguous before the other's enter
    assert order in (["a-enter", "a-exit", "b-enter", "b-exit"], ["b-enter", "b-exit", "a-enter", "a-exit"])
