"""Tests for ``app.technical_analysts.market_structure.MarketStructureAnalyst``."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.quality import FeatureQuality
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.enums.technical_analysis import BreakSequencePattern, StructuralBreakPresence, TechnicalAnalysisDimension, TechnicalAnalystOutcome
from app.technical_analysts.market_structure import MarketStructureAnalyst
from tests.technical_analysts_support import NOW, make_market_structure, make_snapshot, make_swing, make_break, status


def _observation(result, dimension):
    matches = [o for o in result.observations if o.dimension is dimension]
    assert len(matches) == 1
    return matches[0]


def _swing_and_break(*, direction: BreakDirection, candle_time, break_time) -> tuple:
    kind = SwingKind.HIGH if direction is BreakDirection.UPWARD_BREAK else SwingKind.LOW
    swing = make_swing(kind=kind, candle_time=candle_time, confirmed_at=candle_time + timedelta(minutes=2))
    brk = make_break(direction=direction, swing=swing, break_candle_time=break_time, break_close=Decimal("100"))
    return swing, brk


def test_latest_upward_break() -> None:
    swing, brk = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=NOW - timedelta(minutes=10), break_time=NOW - timedelta(minutes=1))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing,), breaks=(brk,)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION).value == BreakDirection.UPWARD_BREAK.value


def test_latest_downward_break() -> None:
    swing, brk = _swing_and_break(direction=BreakDirection.DOWNWARD_BREAK, candle_time=NOW - timedelta(minutes=10), break_time=NOW - timedelta(minutes=1))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing,), breaks=(brk,)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION).value == BreakDirection.DOWNWARD_BREAK.value


def test_valid_no_break_case_is_not_unavailable() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(), breaks=(), block_status=status(FeatureQuality.VALID, sample_count=20)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert _observation(result, TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE).value == StructuralBreakPresence.NO_BREAK_CONFIRMED.value
    dims = [o.dimension for o in result.observations]
    assert TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION not in dims


def test_break_presence_confirmed_when_break_exists() -> None:
    swing, brk = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=NOW - timedelta(minutes=10), break_time=NOW - timedelta(minutes=1))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing,), breaks=(brk,)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE).value == StructuralBreakPresence.BREAK_CONFIRMED.value


def test_repeated_break_directions() -> None:
    t0 = NOW - timedelta(minutes=30)
    swing1, brk1 = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=t0, break_time=t0 + timedelta(minutes=5))
    swing2, brk2 = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=t0 + timedelta(minutes=6), break_time=t0 + timedelta(minutes=10))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing1, swing2), breaks=(brk1, brk2)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BREAK_SEQUENCE_PATTERN).value == BreakSequencePattern.REPEATED_DIRECTION.value


def test_alternating_break_directions() -> None:
    t0 = NOW - timedelta(minutes=30)
    swing1, brk1 = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=t0, break_time=t0 + timedelta(minutes=5))
    swing2, brk2 = _swing_and_break(direction=BreakDirection.DOWNWARD_BREAK, candle_time=t0 + timedelta(minutes=6), break_time=t0 + timedelta(minutes=10))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing1, swing2), breaks=(brk1, brk2)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BREAK_SEQUENCE_PATTERN).value == BreakSequencePattern.ALTERNATING.value


def test_fewer_than_two_breaks_is_insufficient_data() -> None:
    swing, brk = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=NOW - timedelta(minutes=10), break_time=NOW - timedelta(minutes=1))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing,), breaks=(brk,)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BREAK_SEQUENCE_PATTERN).value == BreakSequencePattern.INSUFFICIENT_DATA.value


def test_zero_breaks_break_sequence_is_insufficient_data() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(), breaks=()))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert _observation(result, TechnicalAnalysisDimension.BREAK_SEQUENCE_PATTERN).value == BreakSequencePattern.INSUFFICIENT_DATA.value


def test_partial_quality_propagates() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(block_status=status(FeatureQuality.PARTIAL, sample_count=3)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.PARTIAL


def test_stale_quality_propagates() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(block_status=status(FeatureQuality.STALE, sample_count=3)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ANALYZED
    assert result.quality is FeatureQuality.STALE


def test_unavailable_block_causes_abstention() -> None:
    snapshot = make_snapshot(market_structure=make_market_structure(block_status=status(FeatureQuality.UNAVAILABLE, sample_count=0)))
    result = MarketStructureAnalyst().analyze(snapshot)
    assert result.status is TechnicalAnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert result.observations == ()


def test_no_bos_choch_reversal_continuation_vocabulary() -> None:
    swing, brk = _swing_and_break(direction=BreakDirection.UPWARD_BREAK, candle_time=NOW - timedelta(minutes=10), break_time=NOW - timedelta(minutes=1))
    snapshot = make_snapshot(market_structure=make_market_structure(swings=(swing,), breaks=(brk,)))
    result = MarketStructureAnalyst().analyze(snapshot)
    forbidden = ("BOS", "CHOCH", "REVERSAL", "CONTINUATION", "BULLISH", "BEARISH", "RECENT", "OLD", "FRESH")
    for observation in result.observations:
        for term in forbidden:
            assert term not in observation.value.upper()
