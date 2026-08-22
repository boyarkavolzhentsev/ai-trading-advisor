"""Raw market state contract."""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.enums.market import MarketType, Timeframe
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.data_quality import DataQuality


class MarketSnapshot(DomainModel):
    """Point-in-time raw market state for one symbol.

    Carries only observed values. No indicators, no derived analytics: those
    belong to ``TechnicalSnapshot`` and future calculator components.
    """

    symbol: Symbol
    market: MarketType
    timestamp: Timestamp
    timeframe: Timeframe
    price: Price
    bid: Price | None = None
    ask: Price | None = None
    spread: Price | None = None
    data_quality: DataQuality

    @model_validator(mode="after")
    def _validate_quotes(self) -> Self:
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self
