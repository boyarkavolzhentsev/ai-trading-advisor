"""BoundedBuffer overflow behaviour."""

from __future__ import annotations

import pytest

from app.market_data.realtime.buffers import BoundedBuffer


def test_buffer_holds_up_to_maxlen() -> None:
    buffer: BoundedBuffer[int] = BoundedBuffer(maxlen=3)
    for value in (1, 2, 3):
        buffer.append(value)
    assert list(buffer) == [1, 2, 3]
    assert len(buffer) == 3
    assert buffer.dropped_count == 0


def test_buffer_drops_oldest_on_overflow() -> None:
    buffer: BoundedBuffer[int] = BoundedBuffer(maxlen=3)
    for value in (1, 2, 3, 4, 5):
        buffer.append(value)
    assert list(buffer) == [3, 4, 5]
    assert len(buffer) == 3
    assert buffer.dropped_count == 2


def test_latest_returns_most_recent_n_oldest_first() -> None:
    buffer: BoundedBuffer[int] = BoundedBuffer(maxlen=5)
    for value in range(10):
        buffer.append(value)
    assert buffer.latest(3) == [7, 8, 9]
    assert buffer.latest() == [5, 6, 7, 8, 9]


def test_rejects_non_positive_maxlen() -> None:
    with pytest.raises(ValueError, match="maxlen must be >= 1"):
        BoundedBuffer(maxlen=0)


def test_maxlen_property() -> None:
    assert BoundedBuffer[int](maxlen=42).maxlen == 42
