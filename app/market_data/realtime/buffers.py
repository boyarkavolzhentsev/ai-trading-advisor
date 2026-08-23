"""Bounded in-memory buffers for real-time market data.

Every buffer here has an explicit, finite capacity - unbounded growth is not
allowed anywhere in this module. This is scratch/working state only; nothing
here is persisted.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedBuffer(Generic[T]):
    """Fixed-capacity ring buffer with a drop-oldest overflow policy.

    Used for recent-history windows (liquidations, trades, closed taker-flow
    buckets) that a future narrow Flow sub-agent can read from.
    """

    def __init__(self, maxlen: int) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be >= 1")
        self._items: deque[T] = deque(maxlen=maxlen)
        self._dropped_count = 0

    @property
    def maxlen(self) -> int:
        assert self._items.maxlen is not None
        return self._items.maxlen

    @property
    def dropped_count(self) -> int:
        """Number of items evicted so far because the buffer was full."""
        return self._dropped_count

    def append(self, item: T) -> None:
        if len(self._items) == self._items.maxlen:
            self._dropped_count += 1
        self._items.append(item)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def latest(self, count: int | None = None) -> list[T]:
        """Return up to ``count`` most recent items, oldest first."""
        items = list(self._items)
        if count is None:
            return items
        return items[-count:]


__all__ = ["BoundedBuffer"]
