"""Actionable trade setup contract."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.market import MarketType
from app.core.enums.trade import TradeDirection
from app.core.models.base import (
    Confidence,
    DomainModel,
    Price,
    Ratio,
    Symbol,
    Timestamp,
)


class EntryZone(DomainModel):
    """Price band an entry is acceptable in."""

    low: Price
    high: Price

    @model_validator(mode="after")
    def _validate_bounds(self) -> Self:
        if self.high < self.low:
            raise ValueError("entry zone high must be greater than or equal to low")
        return self


class TradeSetup(DomainModel):
    """A concrete, time-bounded trade recommendation.

    Business contract: a ``LONG``/``SHORT`` recommendation is only executable
    inside a fixed execution window that starts at ``signal_time``. The window
    length lives in ``app.core.config.SIGNAL_EXECUTION_WINDOW`` (5 minutes) and
    is never hard-coded in logic. Here we only require that ``valid_until``
    lies after ``signal_time``; expiry timers are not implemented yet.

    Entry is expressed either as a single ``entry_price`` or as an
    ``entry_zone`` - exactly one of the two.
    """

    symbol: Symbol
    market: MarketType
    direction: TradeDirection
    signal_time: Timestamp
    valid_until: Timestamp
    entry_price: Price | None = None
    entry_zone: EntryZone | None = None
    stop_loss: Price
    take_profit_levels: list[Price] = Field(default_factory=list)
    risk_reward: Ratio | None = None
    confidence: Confidence

    @model_validator(mode="after")
    def _validate_window(self) -> Self:
        if self.valid_until <= self.signal_time:
            raise ValueError("valid_until must be after signal_time")
        return self

    @model_validator(mode="after")
    def _validate_entry(self) -> Self:
        if (self.entry_price is None) == (self.entry_zone is None):
            raise ValueError("provide exactly one of entry_price or entry_zone")
        return self
