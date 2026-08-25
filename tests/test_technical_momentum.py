"""Tests for app.technical.momentum: rate of change and Wilder RSI."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.technical.momentum import (
    RSI_FLAT_SERIES_VALUE,
    RSI_NO_GAIN_VALUE,
    RSI_NO_LOSS_VALUE,
    compute_momentum_features,
)
from tests.technical_support import candles_from_closes


def _compute(closes: list[str], *, roc_period: int, rsi_period: int):
    candles = candles_from_closes(closes)
    return compute_momentum_features(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=Timeframe.M1,
        candles=candles, roc_period=roc_period, rsi_period=rsi_period, source="test",
    )


def test_exact_roc() -> None:
    result = _compute(["100", "106", "104"], roc_period=2, rsi_period=2)
    assert result.roc == Decimal("4")  # (104-100)/100*100


def test_exact_wilder_rsi() -> None:
    result = _compute(["100", "106", "104"], roc_period=2, rsi_period=2)
    # gains=[6,0] losses=[0,2]; avg_gain=3, avg_loss=1; rs=3; rsi=100-100/4=75.
    assert result.rsi == Decimal("75")
    assert result.status.quality is FeatureQuality.VALID


def test_rsi_no_loss_case() -> None:
    result = _compute(["100", "102", "105"], roc_period=2, rsi_period=2)
    assert result.rsi == RSI_NO_LOSS_VALUE == Decimal("100")


def test_rsi_no_gain_case() -> None:
    result = _compute(["105", "102", "100"], roc_period=2, rsi_period=2)
    assert result.rsi == RSI_NO_GAIN_VALUE == Decimal("0")


def test_rsi_flat_series_case() -> None:
    result = _compute(["100", "100", "100"], roc_period=2, rsi_period=2)
    assert result.rsi == RSI_FLAT_SERIES_VALUE == Decimal("50")
    assert result.status.quality is FeatureQuality.VALID


def test_insufficient_warmup_both_none() -> None:
    result = _compute(["100", "102"], roc_period=5, rsi_period=5)
    assert result.roc is None
    assert result.rsi is None
    assert result.status.quality is FeatureQuality.PARTIAL


def test_insufficient_warmup_roc_only() -> None:
    result = _compute(["100", "106", "104"], roc_period=5, rsi_period=2)
    assert result.roc is None
    assert result.rsi is not None
    assert result.status.quality is FeatureQuality.PARTIAL


def test_no_candles_is_unavailable() -> None:
    result = _compute([], roc_period=2, rsi_period=2)
    assert result.status.quality is FeatureQuality.UNAVAILABLE
    assert result.roc is None
    assert result.rsi is None
