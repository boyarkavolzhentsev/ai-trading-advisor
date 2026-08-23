"""Provider-agnostic real-time market data contracts.

Narrow, one capability per Protocol - mirrors ``app.market_data.protocols``'s
REST contracts, and deliberately avoids one umbrella interface. No
implementation described here understands trading signals; each only
describes what a real-time source of one kind of data must offer.

Best bid/ask real-time streaming (``bookTicker``) is deferred; no protocol
for it exists yet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.order_book import OrderBookSnapshot
from app.core.models.stream_health import StreamHealth
from app.core.models.trade_event import TradeEvent


@runtime_checkable
class LiquidationStream(Protocol):
    """Real-time source of forced-liquidation events for one venue."""

    def liquidations(self, symbol: str | None = None) -> AsyncIterator[LiquidationEvent]:
        """Yield liquidation events as they occur.

        ``symbol=None`` means "all markets", where the provider supports it.
        """
        ...

    def health(self) -> StreamHealth:
        """Current health/freshness verdict of this stream."""
        ...


@runtime_checkable
class TradeStream(Protocol):
    """Real-time source of trade/aggregate-trade prints for one venue."""

    def trades(self, symbol: str) -> AsyncIterator[TradeEvent]:
        """Yield trade prints for ``symbol`` as they occur."""
        ...

    def health(self) -> StreamHealth:
        """Current health/freshness verdict of this stream."""
        ...


@runtime_checkable
class OrderBookStream(Protocol):
    """Real-time, synchronized order book source for one venue."""

    def order_book(self, symbol: str) -> AsyncIterator[OrderBookSnapshot]:
        """Yield a freshly materialized snapshot each time the local book
        for ``symbol`` changes state (an applied update, or a fresh snapshot
        after a resync)."""
        ...

    def health(self) -> StreamHealth:
        """Current health/freshness verdict of this stream."""
        ...


@runtime_checkable
class MarkPriceStream(Protocol):
    """Real-time source of mark price / funding rate updates for one venue."""

    def mark_price(self, symbol: str) -> AsyncIterator[FundingRate]:
        """Yield mark price / funding updates for ``symbol`` as they occur."""
        ...

    def health(self) -> StreamHealth:
        """Current health/freshness verdict of this stream."""
        ...


__all__ = ["LiquidationStream", "MarkPriceStream", "OrderBookStream", "TradeStream"]
