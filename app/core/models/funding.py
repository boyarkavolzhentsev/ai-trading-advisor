"""Perpetual futures funding rate contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Price, Symbol, Timestamp


class FundingRate(DomainModel):
    """Funding rate state of a perpetual contract, as last computed by the venue.

    ``funding_rate`` is signed: a negative value means shorts pay longs.
    ``funding_interval_hours`` is ``None`` when the venue does not disclose the
    interval for this symbol - it is never assumed to be any particular
    duration.
    """

    symbol: Symbol
    contract_type: ContractType
    funding_rate: Decimal
    funding_interval_hours: Annotated[int, Field(gt=0)] | None = None
    mark_price: Price
    index_price: Price
    next_funding_time: Timestamp | None = None
    source: str = Field(min_length=1)
    timestamp: Timestamp
