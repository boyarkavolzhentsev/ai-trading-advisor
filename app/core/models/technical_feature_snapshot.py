"""Stage 3A deterministic technical analytics composition root.

One ``TechnicalFeatureSnapshot`` per ``(symbol, contract_type, timeframe)``
observation. Every nested block is always present and carries its own
``FeatureStatus`` - a block with no usable history reports
``FeatureQuality.UNAVAILABLE`` rather than being omitted, mirroring
``FlowFeatureSnapshot``'s composition pattern one contour over. Carries only
already-computed facts - no trend/regime label, no BUY/SELL recommendation,
no interpretation, and no ``FlowFeatureSnapshot``/flow-analyst coupling of
any kind.

Deliberately distinct from the legacy, unused
``app.core.models.technical.TechnicalSnapshot`` placeholder, which is left
untouched by Stage 3A and superseded by this model family.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.candle import OHLCVCandle
from app.core.models.candle_structure_features import CandleStructureFeatures
from app.core.models.feature_status import FeatureStatus
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.momentum_features import MomentumFeatures
from app.core.models.moving_average_features import MovingAverageFeatures
from app.core.models.range_state_features import RangeStateFeatures
from app.core.models.trend_features import TrendFeatures
from app.core.models.volatility_features import VolatilityFeatures


class TechnicalFeatureSnapshot(DomainModel):
    """Synchronized deterministic technical analytics snapshot."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    observation_time: Timestamp
    last_closed_candle_time: Timestamp | None = None
    live_candle: OHLCVCandle | None = None
    trend: TrendFeatures
    market_structure: MarketStructureFeatures
    volatility: VolatilityFeatures
    momentum: MomentumFeatures
    moving_average: MovingAverageFeatures
    candle_structure: CandleStructureFeatures
    range_state: RangeStateFeatures
    status: FeatureStatus
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_live_candle_after_last_closed(self) -> Self:
        if self.live_candle is not None and self.last_closed_candle_time is not None:
            if self.live_candle.timestamp <= self.last_closed_candle_time:
                raise ValueError("live_candle.timestamp must be strictly after last_closed_candle_time")
        return self


__all__ = ["TechnicalFeatureSnapshot"]
