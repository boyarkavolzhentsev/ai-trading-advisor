"""Deterministic Stage 3A market-structure calculator: confirmed fractal
swings and objective close-based structural breaks.

Swing definition: an N-left/N-right fractal. ``high_i`` (``low_i``) must be
strictly greater (less) than every one of its ``left_bars`` left-neighbor
highs (lows) and every one of its ``right_bars`` right-neighbor highs
(lows). Equal values never qualify - a tie is not a swing. A swing is only
ever emitted once its ``right_bars`` right-side neighbors have themselves
CLOSED: ``confirmed_at`` is exactly the timestamp of the ``right_bars``-th
right neighbor, so no swing is ever reported for the most recent
``right_bars`` closed candles (no lookahead leakage).

Structural break: the first later CLOSED candle whose ``close`` (never a
wick) strictly exceeds an already-confirmed swing high (``UPWARD_BREAK``)
or falls strictly below an already-confirmed swing low
(``DOWNWARD_BREAK``). By construction, no candle within a swing's own
``right_bars`` confirmation window can ever break it - the fractal
condition already requires every one of those candles' highs/lows to stay
strictly inside the swing's extreme, so break scanning starts strictly
after ``confirmed_at`` with no special-casing required. Once a swing is
broken it is retired: subsequent candles never re-emit a second break for
the same swing. No tolerance band in v1 - the comparison is exact.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.models.candle import OHLCVCandle
from app.core.models.market_structure_features import MarketStructureFeatures, StructuralBreak, SwingPoint
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid

DEFAULT_LEFT_BARS = 2
DEFAULT_RIGHT_BARS = 2


def _detect_swings(
    candles: Sequence[OHLCVCandle], *, left_bars: int, right_bars: int
) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    n = len(candles)
    for i in range(left_bars, n - right_bars):
        pivot = candles[i]
        left = candles[i - left_bars : i]
        right = candles[i + 1 : i + 1 + right_bars]

        if all(pivot.high > c.high for c in left) and all(pivot.high > c.high for c in right):
            swings.append(
                SwingPoint(
                    kind=SwingKind.HIGH,
                    candle_time=pivot.timestamp,
                    price=pivot.high,
                    confirmed_at=candles[i + right_bars].timestamp,
                    left_bars=left_bars,
                    right_bars=right_bars,
                )
            )
        if all(pivot.low < c.low for c in left) and all(pivot.low < c.low for c in right):
            swings.append(
                SwingPoint(
                    kind=SwingKind.LOW,
                    candle_time=pivot.timestamp,
                    price=pivot.low,
                    confirmed_at=candles[i + right_bars].timestamp,
                    left_bars=left_bars,
                    right_bars=right_bars,
                )
            )
    swings.sort(key=lambda s: (s.confirmed_at, s.candle_time, s.kind.value))
    return swings


def _detect_breaks(
    candles: Sequence[OHLCVCandle], swings: Sequence[SwingPoint]
) -> list[StructuralBreak]:
    index_by_time = {c.timestamp: idx for idx, c in enumerate(candles)}
    breaks: list[StructuralBreak] = []
    for swing in swings:
        confirmed_idx = index_by_time.get(swing.confirmed_at)
        if confirmed_idx is None:
            continue
        for candle in candles[confirmed_idx + 1 :]:
            if swing.kind is SwingKind.HIGH and candle.close > swing.price:
                breaks.append(
                    StructuralBreak(
                        direction=BreakDirection.UPWARD_BREAK,
                        broken_swing=swing,
                        break_candle_time=candle.timestamp,
                        break_close=candle.close,
                        confirmed_at=candle.timestamp,
                    )
                )
                break
            if swing.kind is SwingKind.LOW and candle.close < swing.price:
                breaks.append(
                    StructuralBreak(
                        direction=BreakDirection.DOWNWARD_BREAK,
                        broken_swing=swing,
                        break_candle_time=candle.timestamp,
                        break_close=candle.close,
                        confirmed_at=candle.timestamp,
                    )
                )
                break
    breaks.sort(key=lambda b: (b.break_candle_time, b.direction.value))
    return breaks


def compute_market_structure_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    left_bars: int = DEFAULT_LEFT_BARS,
    right_bars: int = DEFAULT_RIGHT_BARS,
    source: str,
) -> MarketStructureFeatures:
    """Compute confirmed swings and structural breaks over CLOSED candles."""
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be >= 1")

    tail = contiguous_tail(candles, timeframe)
    required = left_bars + right_bars + 1

    if not tail:
        status = unavailable("no contiguous closed candles available")
        swings: tuple[SwingPoint, ...] = ()
        breaks: tuple[StructuralBreak, ...] = ()
    else:
        swings_list = _detect_swings(tail, left_bars=left_bars, right_bars=right_bars)
        breaks_list = _detect_breaks(tail, swings_list)
        swings = tuple(swings_list)
        breaks = tuple(breaks_list)
        if len(tail) < required:
            status = partial(
                f"only {len(tail)} contiguous closed candles available, need at least {required} "
                f"for left_bars={left_bars}, right_bars={right_bars}",
                sample_count=len(tail),
            )
        else:
            status = valid(len(tail))

    return MarketStructureFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        left_bars=left_bars,
        right_bars=right_bars,
        swings=swings,
        breaks=breaks,
        status=status,
        source=source,
    )


__all__ = ["DEFAULT_LEFT_BARS", "DEFAULT_RIGHT_BARS", "compute_market_structure_features"]
