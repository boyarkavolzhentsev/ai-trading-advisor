"""Provider-agnostic market data contract.

Core and future application code depend on this Protocol only, never on a
concrete venue. Every method returns typed domain models and raises
``MarketDataError`` subclasses on failure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.instrument import InstrumentMetadata
from app.core.models.quote import BidAskQuote, PriceQuote

DEFAULT_OHLCV_LIMIT = 100
"""Number of candles requested when the caller does not specify a limit."""


@runtime_checkable
class MarketDataProvider(Protocol):
    """Read-only market data source for one venue."""

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Return the last traded price of ``symbol``."""
        ...

    def get_bid_ask(self, symbol: str) -> BidAskQuote:
        """Return the best bid and ask of ``symbol``."""
        ...

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
    ) -> list[OHLCVCandle]:
        """Return up to ``limit`` most recent candles, oldest first."""
        ...

    def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        """Return the venue specification of ``symbol``."""
        ...


__all__ = ["DEFAULT_OHLCV_LIMIT", "MarketDataProvider"]
