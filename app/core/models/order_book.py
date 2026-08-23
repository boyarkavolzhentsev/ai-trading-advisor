"""Order book snapshot and incremental-update contracts.

``OrderBookSnapshot`` is a point-in-time view (REST, or a synchronized
real-time book materialized on demand) - no imbalance or pressure
calculation. ``OrderBookDeltaEvent`` is the raw incremental update a
depth-diff WebSocket stream delivers, prior to being applied by a
synchronizer; it is not itself a usable book. Levels are carried in the
order the venue returned them (best price first) for snapshots.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Price, Symbol, Timestamp, Volume

UpdateId = Annotated[int, Field(ge=0)]


class OrderBookLevel(DomainModel):
    """One price level of an order book side."""

    price: Price
    quantity: Volume


class OrderBookSnapshot(DomainModel):
    """Bounded, point-in-time order book snapshot of one symbol."""

    symbol: Symbol
    contract_type: ContractType
    last_update_id: UpdateId
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    source: str = Field(min_length=1)
    timestamp: Timestamp

    @model_validator(mode="after")
    def _validate_book(self) -> Self:
        if self.bids and self.asks and self.asks[0].price < self.bids[0].price:
            raise ValueError("best ask must not be below best bid")
        return self


class OrderBookDeltaEvent(DomainModel):
    """Raw incremental order book update, prior to synchronization.

    ``previous_final_update_id`` is the Futures continuity field (Binance's
    ``pu``): each event's value should equal the previously applied event's
    ``final_update_id``. It is ``None`` for a provider/contract family that
    does not report this (e.g. a future Spot mapper). A quantity of ``0`` in
    ``bid_updates``/``ask_updates`` means "remove this price level".
    """

    symbol: Symbol
    contract_type: ContractType
    first_update_id: UpdateId
    final_update_id: UpdateId
    previous_final_update_id: UpdateId | None = None
    bid_updates: list[OrderBookLevel]
    ask_updates: list[OrderBookLevel]
    event_time: Timestamp
    transaction_time: Timestamp | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_update_ids(self) -> Self:
        if self.final_update_id < self.first_update_id:
            raise ValueError("final_update_id must be greater than or equal to first_update_id")
        return self
