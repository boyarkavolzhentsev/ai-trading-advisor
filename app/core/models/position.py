"""Position / trade record contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from app.core.enums.market import MarketType
from app.core.enums.trade import TradeDirection, TradeStatus
from app.core.models.base import (
    MutableDomainModel,
    Price,
    Symbol,
    Timestamp,
)


class PositionRecord(MutableDomainModel):
    """Lifecycle record of one recommended trade.

    Mutable by design: the future MT5 tracker (read-only against the broker)
    fills in fill, exit and P&L fields as they become known. Everything the
    tracker supplies is optional so a record can exist from the moment a
    recommendation is issued - including recommendations that are never filled.

    ``pnl`` and ``pnl_percent`` are signed and are not computed here.
    """

    trade_id: str = Field(min_length=1)
    symbol: Symbol
    market: MarketType
    direction: TradeDirection
    signal_time: Timestamp
    valid_until: Timestamp
    status: TradeStatus = TradeStatus.PENDING
    planned_entry: Price
    actual_entry: Price | None = None
    actual_entry_time: Timestamp | None = None
    stop_loss: Price
    take_profit_levels: list[Price] = Field(default_factory=list)
    exit_price: Price | None = None
    exit_time: Timestamp | None = None
    pnl: Decimal | None = None
    pnl_percent: Decimal | None = None

    @model_validator(mode="after")
    def _validate_timeline(self) -> Self:
        if self.valid_until <= self.signal_time:
            raise ValueError("valid_until must be after signal_time")
        if (
            self.actual_entry_time is not None
            and self.exit_time is not None
            and self.exit_time < self.actual_entry_time
        ):
            raise ValueError("exit_time cannot be before actual_entry_time")
        return self
