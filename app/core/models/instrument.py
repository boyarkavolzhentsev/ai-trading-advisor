"""Instrument specification contract.

Describes what a venue allows for one symbol. It is collected now so future
money management can size positions against real venue constraints; no lot
sizing or rounding logic is implemented here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.instrument import InstrumentStatus
from app.core.models.base import DomainModel, Symbol, Timestamp

Asset = Annotated[str, Field(min_length=1, max_length=32)]
"""Asset code as reported by the venue (e.g. ``BTC``, ``USDT``)."""


class InstrumentMetadata(DomainModel):
    """Venue-reported specification of a tradable instrument."""

    symbol: Symbol
    base_asset: Asset
    quote_asset: Asset
    status: InstrumentStatus
    tick_size: Annotated[Decimal, Field(gt=0)]
    price_precision: Annotated[int, Field(ge=0)]
    step_size: Annotated[Decimal, Field(gt=0)]
    quantity_precision: Annotated[int, Field(ge=0)]
    min_quantity: Annotated[Decimal, Field(ge=0)] | None = None
    max_quantity: Annotated[Decimal, Field(ge=0)] | None = None
    min_notional: Annotated[Decimal, Field(ge=0)] | None = None
    source: str = Field(min_length=1)
    timestamp: Timestamp

    @model_validator(mode="after")
    def _validate_quantity_bounds(self) -> Self:
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.max_quantity < self.min_quantity
        ):
            raise ValueError("max_quantity must be greater than or equal to min_quantity")
        return self
