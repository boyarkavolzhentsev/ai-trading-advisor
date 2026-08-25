"""Deterministic Stage 3A momentum calculator: rate of change and Wilder RSI.

RSI uses Wilder's original gain/loss smoothing, matching the ATR warm-up
convention exactly: ``initial_avg_gain``/``initial_avg_loss`` are the
arithmetic mean of the first ``rsi_period`` gains/losses, and every
subsequent value applies the Wilder recursion
``avg_t = ((avg_(t-1) * (period - 1)) + value_t) / period`` - i.e.
``rsi_period + 1`` contiguous closed candles are needed before any RSI value
exists, exactly mirroring ``app.technical.volatility``'s ATR warm-up.

Deterministic edge cases (never a division by zero):

- ``avg_loss == 0`` (no losses in the smoothed window) -> ``RSI = 100``.
- ``avg_gain == 0`` (no gains in the smoothed window) -> ``RSI = 0``.
- both zero (a perfectly flat price series over the whole window) -> the
  explicit, documented flat-series convention ``RSI = 50`` (no directional
  movement at all, reported as the neutral midpoint rather than an
  arbitrarily chosen extreme).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.momentum_features import MomentumFeatures
from app.technical.alignment import contiguous_tail
from app.technical.quality import partial, unavailable, valid

DEFAULT_ROC_PERIOD = 12
DEFAULT_RSI_PERIOD = 14

RSI_FLAT_SERIES_VALUE = Decimal(50)
RSI_NO_LOSS_VALUE = Decimal(100)
RSI_NO_GAIN_VALUE = Decimal(0)


def _gains_and_losses(candles: Sequence[OHLCVCandle]) -> tuple[list[Decimal], list[Decimal]]:
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for prev, curr in zip(candles, candles[1:]):
        change = curr.close - prev.close
        gains.append(change if change > 0 else Decimal(0))
        losses.append(-change if change < 0 else Decimal(0))
    return gains, losses


def wilder_rsi(gains: Sequence[Decimal], losses: Sequence[Decimal], period: int) -> Decimal | None:
    """Wilder-smoothed RSI from parallel gain/loss series.

    ``None`` if fewer than ``period`` gain/loss observations are supplied.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period], Decimal(0)) / period
    avg_loss = sum(losses[:period], Decimal(0)) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_gain == 0 and avg_loss == 0:
        return RSI_FLAT_SERIES_VALUE
    if avg_loss == 0:
        return RSI_NO_LOSS_VALUE
    if avg_gain == 0:
        return RSI_NO_GAIN_VALUE

    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (1 + rs))


def compute_momentum_features(
    *,
    symbol: str,
    contract_type: ContractType,
    timeframe: Timeframe,
    candles: Sequence[OHLCVCandle],
    roc_period: int = DEFAULT_ROC_PERIOD,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    source: str,
) -> MomentumFeatures:
    """Compute deterministic momentum facts over CLOSED, contiguous candles."""
    if roc_period < 1:
        raise ValueError("roc_period must be >= 1")
    if rsi_period < 1:
        raise ValueError("rsi_period must be >= 1")

    tail = contiguous_tail(candles, timeframe)

    roc = None
    if len(tail) >= roc_period + 1:
        base = tail[-(roc_period + 1)].close
        if base > 0:
            roc = (tail[-1].close - base) / base * 100

    gains, losses = _gains_and_losses(tail)
    rsi = wilder_rsi(gains, losses, rsi_period)

    if not tail:
        status = unavailable("no contiguous closed candles available")
    elif roc is None and rsi is None:
        status = partial(
            f"only {len(tail)} contiguous closed candles available; roc needs {roc_period + 1}, "
            f"rsi needs {rsi_period + 1}",
            sample_count=len(tail),
        )
    elif roc is None:
        status = partial(
            f"only {len(tail)} contiguous closed candles available, roc needs {roc_period + 1}",
            sample_count=len(tail),
        )
    elif rsi is None:
        status = partial(
            f"only {len(tail)} contiguous closed candles available, rsi needs {rsi_period + 1}",
            sample_count=len(tail),
        )
    else:
        status = valid(len(tail))

    return MomentumFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        roc_period=roc_period,
        rsi_period=rsi_period,
        roc=roc,
        rsi=rsi,
        status=status,
        source=source,
    )


__all__ = [
    "DEFAULT_RSI_PERIOD",
    "DEFAULT_ROC_PERIOD",
    "RSI_FLAT_SERIES_VALUE",
    "RSI_NO_GAIN_VALUE",
    "RSI_NO_LOSS_VALUE",
    "compute_momentum_features",
    "wilder_rsi",
]
