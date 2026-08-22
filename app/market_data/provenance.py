"""Origin record of a single market data fetch.

Answers "where did this number come from" for future auditability. It is built
per request by the provider adapter and is not persisted anywhere in this
stage.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp


class MarketDataSource(StrEnum):
    """Kind of endpoint a value was fetched from."""

    TICKER_PRICE = "ticker_price"
    BOOK_TICKER = "book_ticker"
    KLINES = "klines"
    EXCHANGE_INFO = "exchange_info"


class MarketDataProvenance(DomainModel):
    """Where one piece of market data came from, and when."""

    provider: str = Field(min_length=1)
    source: MarketDataSource
    symbol: Symbol
    timeframe: Timeframe | None = None
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label used as ``DataQuality.source``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["MarketDataProvenance", "MarketDataSource"]
