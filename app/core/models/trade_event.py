"""Real-time trade / aggregate-trade contract.

Carries only the exchange-reported taker side and observed volumes - no
interpretation. ``side`` is a direct transcription of the provider's
maker/taker flag, never inferred (see the Binance real-time mapper for the
exact ``m`` -> ``side`` transcription).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.base import DomainModel, Price, Symbol, Timestamp, Volume

TradeId = Annotated[int, Field(ge=0)]


class TradeEvent(DomainModel):
    """One real-time trade or aggregated-trade print.

    ``first_trade_id``/``last_trade_id`` are populated only for aggregate
    trades (a range of underlying trades merged by the provider); they are
    ``None`` for a raw individual trade print.
    """

    symbol: Symbol
    contract_type: ContractType
    trade_id: TradeId
    price: Price
    quantity: Volume
    quote_quantity: Volume | None = None
    side: OrderSide
    first_trade_id: TradeId | None = None
    last_trade_id: TradeId | None = None
    timestamp: Timestamp
    source: str = Field(min_length=1)
