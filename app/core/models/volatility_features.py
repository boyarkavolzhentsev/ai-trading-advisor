"""Deterministic Stage 3A volatility-feature contract.

True range, Wilder-smoothed ATR, realized volatility, rolling range and an
ATR-relative range-expansion ratio - all plain numeric facts, never a
"high"/"low"/"extreme" label. ``realized_volatility`` is the sample
(``ddof=1``) standard deviation of per-candle fractional returns
(``close_i/close_{i-1} - 1``) - a raw fraction, not a percentage and not
annualized.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol
from app.core.models.feature_status import FeatureStatus


class VolatilityFeatures(DomainModel):
    """Deterministic volatility facts of one symbol/timeframe."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    atr_period: int = Field(ge=1)
    volatility_lookback: int = Field(ge=2)
    true_range: Decimal | None = None
    atr: Decimal | None = None
    realized_volatility: Decimal | None = None
    rolling_range: Decimal | None = None
    range_expansion_ratio: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["VolatilityFeatures"]
