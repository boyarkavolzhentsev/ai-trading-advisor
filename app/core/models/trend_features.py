"""Deterministic Stage 3A trend-feature contract.

Pure numeric facts derived from a maximal contiguous run of CLOSED candles:
return, OLS close-price slope, higher-high/higher-low/lower-high/lower-low
counts, and directional persistence. Never a trend-state label - no
UPTREND/DOWNTREND, no bullish/bearish, no trend confidence. Classifying
these numbers into a state is a future Stage 3B concern.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol
from app.core.models.feature_status import FeatureStatus


class TrendFeatures(DomainModel):
    """Deterministic trend facts of one symbol/timeframe over a lookback."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    lookback: int = Field(ge=2)
    return_pct: Decimal | None = None
    slope: Decimal | None = None
    higher_high_count: int = Field(ge=0, default=0)
    higher_low_count: int = Field(ge=0, default=0)
    lower_high_count: int = Field(ge=0, default=0)
    lower_low_count: int = Field(ge=0, default=0)
    directional_persistence: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["TrendFeatures"]
