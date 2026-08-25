"""Tests for app.technical.market_structure: confirmed fractal swings and
objective close-based structural breaks."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical import BreakDirection, SwingKind
from app.technical.market_structure import compute_market_structure_features
from tests.technical_support import candle


def _compute(candles, left_bars=2, right_bars=2):
    return compute_market_structure_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, left_bars=left_bars, right_bars=right_bars, source="test",
    )


def _high_swing_series(count: int = 5):
    highs = ["100", "101", "105", "102", "101", "100", "99"][:count]
    return [candle(index=i, close=str(Decimal(h) - 1), high=h, low="90") for i, h in enumerate(highs)]


def _low_swing_series(count: int = 5):
    lows = ["90", "89", "85", "88", "89", "90", "91"][:count]
    return [candle(index=i, close=str(Decimal(low) + 1), high="110", low=low) for i, low in enumerate(lows)]


def test_confirmed_swing_high() -> None:
    candles = _high_swing_series(5)
    result = _compute(candles)
    assert len(result.swings) == 1
    swing = result.swings[0]
    assert swing.kind is SwingKind.HIGH
    assert swing.price == Decimal("105")
    assert swing.candle_time == candles[2].timestamp
    assert swing.confirmed_at == candles[4].timestamp
    assert swing.left_bars == 2
    assert swing.right_bars == 2


def test_confirmed_swing_low() -> None:
    candles = _low_swing_series(5)
    result = _compute(candles)
    assert len(result.swings) == 1
    swing = result.swings[0]
    assert swing.kind is SwingKind.LOW
    assert swing.price == Decimal("85")
    assert swing.candle_time == candles[2].timestamp
    assert swing.confirmed_at == candles[4].timestamp


def test_no_swing_before_right_confirmation() -> None:
    candles = _high_swing_series(4)  # only 1 right neighbor available, need 2
    result = _compute(candles)
    assert result.swings == ()


def test_exact_confirmation_boundary() -> None:
    with_confirmation = _compute(_high_swing_series(5))
    without_confirmation = _compute(_high_swing_series(4))
    assert len(with_confirmation.swings) == 1
    assert without_confirmation.swings == ()


def test_equal_highs_rejected() -> None:
    candles = [
        candle(index=0, close="99", high="100", low="90"),
        candle(index=1, close="100", high="101", low="90"),
        candle(index=2, close="104", high="105", low="90"),
        candle(index=3, close="104", high="105", low="90"),  # tie with pivot
        candle(index=4, close="100", high="101", low="90"),
    ]
    result = _compute(candles)
    assert result.swings == ()


def test_equal_lows_rejected() -> None:
    candles = [
        candle(index=0, close="91", high="110", low="90"),
        candle(index=1, close="90", high="110", low="89"),
        candle(index=2, close="86", high="110", low="85"),
        candle(index=3, close="86", high="110", low="85"),  # tie with pivot
        candle(index=4, close="90", high="110", low="89"),
    ]
    result = _compute(candles)
    assert result.swings == ()


def test_no_lookahead_leakage_extra_future_candles_do_not_change_confirmed_swing() -> None:
    short = _compute(_high_swing_series(5))
    longer = _compute(_high_swing_series(7))
    assert short.swings[0] == longer.swings[0]


def test_insufficient_history_is_unavailable() -> None:
    result = _compute([])
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.swings == ()
    assert result.breaks == ()


def test_partial_when_fewer_than_required_candles() -> None:
    result = _compute(_high_swing_series(3))
    assert result.status.quality is FeatureQuality.PARTIAL


def _swing_high_then_break_series():
    # indices 0-4: swing high 105 at index 2, confirmed at index 4.
    series = _high_swing_series(5)
    wick_only = candle(index=5, close="104.5", high="106", low="103", open_="104")  # wicks above 105, closes below
    breaking = candle(index=6, close="105.5", high="106", low="104", open_="105")  # closes above 105
    continuation = candle(index=7, close="108", high="109", low="107", open_="107.5")  # further beyond, no new break
    return [*series, wick_only, breaking, continuation]


def test_upward_structural_break_is_close_based() -> None:
    candles = _swing_high_then_break_series()
    result = _compute(candles)
    assert len(result.breaks) == 1
    brk = result.breaks[0]
    assert brk.direction is BreakDirection.UPWARD_BREAK
    assert brk.break_candle_time == candles[6].timestamp
    assert brk.break_close == Decimal("105.5")
    assert brk.confirmed_at == candles[6].timestamp
    assert brk.broken_swing.price == Decimal("105")


def test_wick_only_break_rejected() -> None:
    candles = _swing_high_then_break_series()
    result = _compute(candles)
    # candle index 5 wicks above the swing high but closes below it - must
    # never be recorded as the break; the break is index 6's close instead.
    assert all(b.break_candle_time != candles[5].timestamp for b in result.breaks)


def test_repeated_break_not_re_emitted_on_continuation() -> None:
    candles = _swing_high_then_break_series()
    result = _compute(candles)
    # index 7 closes even further beyond the swing high but must not add a
    # second break for the same swing.
    assert len(result.breaks) == 1


def _swing_low_then_break_series():
    series = _low_swing_series(5)  # swing low 85 at index 2, confirmed at index 4
    wick_only = candle(index=5, close="85.5", high="87", low="84", open_="86")  # wicks below 85, closes above
    breaking = candle(index=6, close="84.5", high="86", low="84", open_="85")  # closes below 85
    return [*series, wick_only, breaking]


def test_downward_structural_break_is_close_based() -> None:
    candles = _swing_low_then_break_series()
    result = _compute(candles)
    assert len(result.breaks) == 1
    brk = result.breaks[0]
    assert brk.direction is BreakDirection.DOWNWARD_BREAK
    assert brk.break_candle_time == candles[6].timestamp
    assert brk.break_close == Decimal("84.5")
    assert brk.broken_swing.price == Decimal("85")
