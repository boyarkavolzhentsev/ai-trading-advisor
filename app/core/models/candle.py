"""OHLCV candle contract."""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.models.base import DomainModel, Price, Timestamp, Volume


class OHLCVCandle(DomainModel):
    """A single OHLCV bar as delivered by a data source.

    Structural integrity only: no indicator derivation happens here.
    """

    timestamp: Timestamp
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Volume

    @model_validator(mode="after")
    def _validate_price_range(self) -> Self:
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open must be within the low-high range")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close must be within the low-high range")
        return self
