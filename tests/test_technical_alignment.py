"""Tests for app.technical.alignment: closed-candle policy and contiguity."""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.market import Timeframe
from app.technical.alignment import (
    candle_close_time,
    contiguous_tail,
    expected_open_time,
    is_aligned,
    is_closed,
    split_closed_and_forming,
)
from tests.technical_support import BASE, candle, candles_from_closes


def test_expected_open_time_floors_to_epoch_boundary() -> None:
    ts = BASE + timedelta(minutes=5, seconds=37)
    assert expected_open_time(ts, Timeframe.M1) == BASE + timedelta(minutes=5)
    assert expected_open_time(ts, Timeframe.M5) == BASE + timedelta(minutes=5)
    assert expected_open_time(ts, Timeframe.H1) == BASE


def test_is_aligned_true_for_boundary_false_otherwise() -> None:
    assert is_aligned(BASE + timedelta(minutes=5), Timeframe.M1) is True
    assert is_aligned(BASE + timedelta(minutes=5, seconds=1), Timeframe.M1) is False


def test_candle_close_time_is_timestamp_plus_duration() -> None:
    c = candle(index=0, close="100")
    assert candle_close_time(c, Timeframe.M1) == c.timestamp + timedelta(minutes=1)


def test_is_closed_exact_boundary() -> None:
    c = candle(index=0, close="100")
    close_time = candle_close_time(c, Timeframe.M1)
    assert is_closed(c, Timeframe.M1, close_time) is True
    assert is_closed(c, Timeframe.M1, close_time - timedelta(microseconds=1)) is False
    assert is_closed(c, Timeframe.M1, close_time + timedelta(seconds=1)) is True


def test_split_closed_and_forming_excludes_forming_candle() -> None:
    candles = candles_from_closes(["100", "101", "102"])
    as_of = candles[1].timestamp + timedelta(minutes=1)  # candle[1] closed, candle[2] still forming
    closed, live = split_closed_and_forming(candles, Timeframe.M1, as_of)
    assert [c.timestamp for c in closed] == [candles[0].timestamp, candles[1].timestamp]
    assert live is not None
    assert live.timestamp == candles[2].timestamp


def test_split_closed_and_forming_all_closed_when_as_of_far_enough() -> None:
    candles = candles_from_closes(["100", "101", "102"])
    as_of = candles[-1].timestamp + timedelta(minutes=1)
    closed, live = split_closed_and_forming(candles, Timeframe.M1, as_of)
    assert len(closed) == 3
    assert live is None


def test_split_closed_and_forming_empty_input() -> None:
    closed, live = split_closed_and_forming([], Timeframe.M1, BASE)
    assert closed == []
    assert live is None


def test_contiguous_tail_full_run() -> None:
    candles = candles_from_closes(["100", "101", "102", "103"])
    tail = contiguous_tail(candles, Timeframe.M1)
    assert tail == candles


def test_contiguous_tail_stops_at_gap() -> None:
    candles = candles_from_closes(["100", "101", "102"])
    # Splice in a candle 3 minutes after the last one - a genuine gap.
    gapped = candle(index=5, close="200", base=BASE)
    tail = contiguous_tail([*candles, gapped], Timeframe.M1)
    assert tail == [gapped]


def test_contiguous_tail_empty_input() -> None:
    assert contiguous_tail([], Timeframe.M1) == []


def test_contiguous_tail_single_candle() -> None:
    candles = candles_from_closes(["100"])
    assert contiguous_tail(candles, Timeframe.M1) == candles
