"""Bounded per-(symbol, contract_type) history backing Stage 2A calculators.

Wraps ``app.market_data.realtime.buffers.BoundedBuffer`` directly rather than
reimplementing bounded storage - every buffer here has an explicit, finite
capacity, drop-oldest eviction, and a ``dropped_count`` audit trail already.
``FeatureHistoryStore`` is the narrow shape calculators/engine code should
depend on so a future persistence-backed store can be substituted without
touching any calculator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Self, TypeVar, runtime_checkable

from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookSnapshot
from app.core.models.trade_event import TradeEvent
from app.market_data.realtime.buffers import BoundedBuffer

T = TypeVar("T")

DEFAULT_RAW_CAPACITY = 5000
DEFAULT_ORDER_BOOK_CAPACITY = 500
DEFAULT_OPEN_INTEREST_CAPACITY = 500
DEFAULT_FUNDING_CAPACITY = 500
DEFAULT_SNAPSHOT_CAPACITY = 500


@runtime_checkable
class FeatureHistoryStore(Protocol[T]):
    """Narrow append/read contract a bounded history must satisfy.

    ``BoundedBuffer`` already satisfies this shape structurally; no adapter
    is needed today.
    """

    def append(self, item: T) -> None: ...

    def latest(self, count: int | None = None) -> list[T]: ...


@dataclass(slots=True)
class SymbolFeatureHistory:
    """Bounded raw-event and snapshot history of one ``(symbol, contract_type)``.

    Retention of the raw per-domain buffers should be sized to cover at
    least the widest configured ``AnalyticsWindow`` in use; the snapshot
    buffer is independent and typically much smaller since it holds
    already-reduced output.
    """

    trades: BoundedBuffer[TradeEvent]
    liquidations: BoundedBuffer[LiquidationEvent]
    order_book: BoundedBuffer[OrderBookSnapshot]
    open_interest: BoundedBuffer[OpenInterest]
    funding: BoundedBuffer[FundingRate]
    snapshots: BoundedBuffer[FlowFeatureSnapshot]

    @classmethod
    def with_capacity(
        cls,
        *,
        raw_capacity: int = DEFAULT_RAW_CAPACITY,
        order_book_capacity: int = DEFAULT_ORDER_BOOK_CAPACITY,
        open_interest_capacity: int = DEFAULT_OPEN_INTEREST_CAPACITY,
        funding_capacity: int = DEFAULT_FUNDING_CAPACITY,
        snapshot_capacity: int = DEFAULT_SNAPSHOT_CAPACITY,
    ) -> Self:
        return cls(
            trades=BoundedBuffer(maxlen=raw_capacity),
            liquidations=BoundedBuffer(maxlen=raw_capacity),
            order_book=BoundedBuffer(maxlen=order_book_capacity),
            open_interest=BoundedBuffer(maxlen=open_interest_capacity),
            funding=BoundedBuffer(maxlen=funding_capacity),
            snapshots=BoundedBuffer(maxlen=snapshot_capacity),
        )


__all__ = [
    "DEFAULT_FUNDING_CAPACITY",
    "DEFAULT_OPEN_INTEREST_CAPACITY",
    "DEFAULT_ORDER_BOOK_CAPACITY",
    "DEFAULT_RAW_CAPACITY",
    "DEFAULT_SNAPSHOT_CAPACITY",
    "FeatureHistoryStore",
    "SymbolFeatureHistory",
]
