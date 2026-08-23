"""Forced liquidation event contract.

Raw exchange fact: one forced order the venue reports as a liquidation.
``side`` is the side of that forced order as the venue reports it, not a
directional trading recommendation.
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.base import DomainModel, Price, Symbol, Timestamp, Volume


class LiquidationEvent(DomainModel):
    """One forced-liquidation order reported by a venue."""

    symbol: Symbol
    contract_type: ContractType
    side: OrderSide
    price: Price
    quantity: Volume
    quote_quantity: Volume | None = None
    timestamp: Timestamp
    source: str = Field(min_length=1)
