"""Deterministic Stage 3A range/consolidation contract.

Only the two calibration-free numerical primitives: ``normalized_range``
(rolling high-low range relative to ATR) and ``directional_efficiency``
(net displacement over gross path length, Kaufman-style). No
CONSOLIDATING/RANGING/TRENDING classification and no arbitrary threshold -
those require calibration data this stage does not have.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol
from app.core.models.feature_status import FeatureStatus


class RangeStateFeatures(DomainModel):
    """Deterministic, calibration-free range/consolidation facts."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    lookback: int = Field(ge=2)
    atr_period: int = Field(ge=1)
    rolling_range: Decimal | None = None
    normalized_range: Decimal | None = None
    directional_efficiency: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["RangeStateFeatures"]
