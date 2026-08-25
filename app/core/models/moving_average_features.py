"""Deterministic Stage 3A moving-average contract.

Numeric facts only, keyed by period: SMA, EMA, distance from SMA, and MA
slope. No fast/slow crossover label - no "bullish crossover", no "buy/sell
crossover signal". A consumer wanting a crossover comparison already has
both raw values available via ``sma``/``ema``; classifying that comparison
is a future Stage 3B concern.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Price, Symbol
from app.core.models.feature_status import FeatureStatus


class MovingAverageFeatures(DomainModel):
    """Deterministic moving-average facts of one symbol/timeframe.

    Every dict is keyed by period; a period absent from ``sma``/``ema``
    simply had insufficient contiguous closed-candle history to compute -
    it is never present with a fabricated value.
    """

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    periods: tuple[int, ...]
    sma: dict[int, Price] = Field(default_factory=dict)
    ema: dict[int, Price] = Field(default_factory=dict)
    distance_from_sma_pct: dict[int, Decimal] = Field(default_factory=dict)
    ma_slope: dict[int, Decimal] = Field(default_factory=dict)
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["MovingAverageFeatures"]
