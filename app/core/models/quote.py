"""Live quote contracts produced by market data providers.

These are the smallest typed carriers needed so provider adapters never hand
raw dictionaries to the rest of the system. They describe observed quotes only:
no derived analytics beyond the arithmetic spread.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel, Price, Symbol, Timestamp, Volume


class PriceQuote(DomainModel):
    """Last traded price of one instrument at a point in time."""

    symbol: Symbol
    price: Price
    timestamp: Timestamp
    source: str = Field(min_length=1)


class BidAskQuote(DomainModel):
    """Best bid and best ask of one instrument at a point in time.

    Sizes are optional: not every provider reports them.
    """

    symbol: Symbol
    bid: Price
    ask: Price
    bid_quantity: Volume | None = None
    ask_quantity: Volume | None = None
    timestamp: Timestamp
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_quotes(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self

    @property
    def spread(self) -> Decimal:
        """Absolute ask-minus-bid spread in quote currency."""
        return self.ask - self.bid
