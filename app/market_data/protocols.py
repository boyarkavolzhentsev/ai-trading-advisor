"""Provider-agnostic market data contract.

Core and future application code depend on this Protocol only, never on a
concrete venue. Every method returns typed domain models and raises
``MarketDataError`` subclasses on failure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.funding import FundingRate
from app.core.models.instrument import InstrumentMetadata
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookSnapshot
from app.core.models.quote import BidAskQuote, PriceQuote
from app.core.models.taker_flow import TakerFlowSnapshot

DEFAULT_OHLCV_LIMIT = 100
"""Number of candles requested when the caller does not specify a limit."""

DEFAULT_DEPTH_LIMIT = 100
"""Order book levels requested per side when the caller does not specify a limit."""

DEFAULT_LIQUIDATION_LIMIT = 50
"""Liquidation events requested when the caller does not specify a limit."""


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


@runtime_checkable
class FuturesMarketDataProvider(Protocol):
    """Read-only USD-M perpetual futures market data source for one venue.

    REST-based snapshots only, mirroring ``MarketDataProvider``'s layering for
    a different contract family. A maintained/live order book and a
    real-time funding/mark-price stream are out of scope until a WebSocket
    transport exists.
    """

    def get_funding_rate(self, symbol: str) -> FundingRate:
        """Return the current funding state of ``symbol``."""
        ...

    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Return the current total open interest of ``symbol``."""
        ...

    def get_taker_flow(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
    ) -> list[TakerFlowSnapshot]:
        """Return up to ``limit`` taker buy/sell volume snapshots, oldest first."""
        ...

    def get_order_book_snapshot(
        self,
        symbol: str,
        limit: int = DEFAULT_DEPTH_LIMIT,
    ) -> OrderBookSnapshot:
        """Return a bounded, point-in-time order book snapshot of ``symbol``."""
        ...


@runtime_checkable
class LiquidationProvider(Protocol):
    """Read-only source of recent forced-liquidation events for one venue."""

    def get_recent_liquidations(
        self,
        symbol: str,
        limit: int = DEFAULT_LIQUIDATION_LIMIT,
    ) -> list[LiquidationEvent]:
        """Return up to ``limit`` most recent liquidation events."""
        ...


__all__ = [
    "DEFAULT_DEPTH_LIMIT",
    "DEFAULT_LIQUIDATION_LIMIT",
    "DEFAULT_OHLCV_LIMIT",
    "FuturesMarketDataProvider",
    "LiquidationProvider",
    "MarketDataProvider",
]
