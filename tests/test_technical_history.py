"""Tests for app.technical.history.SymbolTimeframeHistory: bounded storage."""

from __future__ import annotations

from app.technical.history import SymbolTimeframeHistory
from tests.technical_support import candle


def test_default_capacity_positive() -> None:
    history = SymbolTimeframeHistory.with_capacity()
    assert history.candles.maxlen > 0
    assert history.snapshots.maxlen > 0


def test_custom_capacity_honored_and_eviction_tracked() -> None:
    history = SymbolTimeframeHistory.with_capacity(candle_capacity=2, snapshot_capacity=2)
    history.candles.append(candle(index=0, close="100"))
    history.candles.append(candle(index=1, close="101"))
    assert history.candles.dropped_count == 0
    history.candles.append(candle(index=2, close="102"))
    assert history.candles.dropped_count == 1
    assert len(history.candles) == 2


def test_two_histories_are_fully_independent() -> None:
    a = SymbolTimeframeHistory.with_capacity()
    b = SymbolTimeframeHistory.with_capacity()
    a.candles.append(candle(index=0, close="100"))
    assert len(a.candles) == 1
    assert len(b.candles) == 0
