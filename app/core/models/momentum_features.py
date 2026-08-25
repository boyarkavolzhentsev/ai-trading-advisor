"""Deterministic Stage 3A momentum-feature contract.

Rate of change and Wilder-smoothed RSI only - plain numeric facts, never a
"overbought"/"oversold"/bullish/bearish label. No price-acceleration field:
a second derivative of already-noisy OHLC data adds no validated
information over ``roc``/``TrendFeatures.slope`` at this stage.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol
from app.core.models.feature_status import FeatureStatus


class MomentumFeatures(DomainModel):
    """Deterministic momentum facts of one symbol/timeframe."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    roc_period: int = Field(ge=1)
    rsi_period: int = Field(ge=1)
    roc: Decimal | None = None
    rsi: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["MomentumFeatures"]
