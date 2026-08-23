"""Perpetual futures open interest contract."""

from __future__ import annotations

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Symbol, Timestamp, Volume


class OpenInterest(DomainModel):
    """Total outstanding open interest of a contract at a point in time."""

    symbol: Symbol
    contract_type: ContractType
    open_interest: Volume
    source: str = Field(min_length=1)
    timestamp: Timestamp
