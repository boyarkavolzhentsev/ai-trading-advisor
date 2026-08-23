"""Bounded order book snapshot contract.

A point-in-time REST snapshot only: no maintained/live book, no imbalance or
pressure calculation. Levels are carried in the order the venue returned them
(best price first).
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Price, Symbol, Timestamp, Volume


class OrderBookLevel(DomainModel):
    """One price level of an order book side."""

    price: Price
    quantity: Volume


class OrderBookSnapshot(DomainModel):
    """Bounded, point-in-time order book snapshot of one symbol."""

    symbol: Symbol
    contract_type: ContractType
    last_update_id: Annotated[int, Field(ge=0)]
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    source: str = Field(min_length=1)
    timestamp: Timestamp

    @model_validator(mode="after")
    def _validate_book(self) -> Self:
        if self.bids and self.asks and self.asks[0].price < self.bids[0].price:
            raise ValueError("best ask must not be below best bid")
        return self
