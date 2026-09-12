"""Provider-agnostic market data contract.

Core and future application code depend on this Protocol only, never on a
concrete venue. Every method returns typed domain models and raises
``MarketDataError`` subclasses on failure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.enums.market import Timeframe
from app.core.models.base import Timestamp
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

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
    ) -> list[OHLCVCandle]:
        """Return up to ``limit`` most recent candles, oldest first."""
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
class OHLCVProvider(Protocol):
    """Read-only OHLCV-only market data source for one venue/timeframe set.

    The narrowest honest contract a Technical-only consumer needs (MT5 Price
    Authority migration): ``MarketDataProvider``/``FuturesMarketDataProvider``
    each carry unrelated capabilities (current price, bid/ask, instrument
    metadata, funding rate, open interest, taker flow, order book) that a
    Technical-only provider would otherwise have to fake or stub.

    ``as_of`` (Stage A contract-completion corrective review): the
    authoritative observation/cycle time, supplied by the caller - never
    substituted by any provider's own independently-sampled wall clock. A
    native-timeframe provider (e.g. Binance, which returns raw klines
    unfiltered and lets its own caller decide closed-vs-forming) may freely
    IGNORE it; a provider that must derive a timeframe internally (e.g. MT5
    synthesizing H4 from H1 and needing to know which H1 bars are already
    closed) MAY require it and fail deterministically without it. Either way,
    every ``OHLCVProvider`` implementation accepts the keyword - a
    provider-agnostic caller may always pass ``as_of=cycle_as_of`` without
    risking a ``TypeError``, and no implementation may read
    ``datetime.now()`` in its place. One honest contract for every provider,
    not a second cycle-aware protocol: both existing Binance providers and
    the MT5 provider satisfy this identical shape.
    """

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
        *,
        as_of: Timestamp | None = None,
    ) -> list[OHLCVCandle]:
        """Return up to ``limit`` most recent candles, oldest first."""
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
    "OHLCVProvider",
]
