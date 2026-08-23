"""Real-time taker buy/sell volume aggregation.

Rolling fixed-width time buckets built from individual ``TradeEvent``s. Only
CLOSED buckets are ever emitted as ``TakerFlowSnapshot`` - the current,
still-filling bucket stays internal to this module and is never modelled as
a domain contract. No interpretation happens here: this is arithmetic
accumulation of the same buy/sell volumes Stage 1B's REST taker flow already
reports (``TakerFlowSnapshot.total_volume``/``delta``/``buy_ratio`` still
apply unchanged), never a signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.order import OrderSide
from app.core.models.taker_flow import TakerFlowSnapshot
from app.core.models.trade_event import TradeEvent
from app.market_data.timeframes import timeframe_duration


@dataclass(slots=True)
class _OpenBucket:
    bucket_start: datetime
    buy_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    sell_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    buy_quote_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    has_quote_volume: bool = True


class TakerFlowAggregator:
    """Accumulates ``TradeEvent``s into closed ``TakerFlowSnapshot`` windows.

    One instance is scoped to one symbol/timeframe. A trade whose bucket is
    earlier than the currently open bucket (a late, out-of-order arrival for
    an already-closed window) is dropped rather than corrupting the open
    bucket or re-opening a past one.
    """

    def __init__(
        self,
        *,
        symbol: str,
        contract_type: ContractType,
        timeframe: Timeframe,
        source: str,
    ) -> None:
        self._symbol = symbol
        self._contract_type = contract_type
        self._timeframe = timeframe
        self._source = source
        self._duration_seconds = timeframe_duration(timeframe).total_seconds()
        self._open: _OpenBucket | None = None

    def add_trade(self, trade: TradeEvent) -> TakerFlowSnapshot | None:
        """Fold ``trade`` into the current bucket.

        Returns the just-closed ``TakerFlowSnapshot`` if this trade started a
        new bucket, else ``None`` (including when the trade was dropped as
        late/out-of-order).
        """
        bucket_start = self._bucket_start_for(trade.timestamp)
        closed: TakerFlowSnapshot | None = None

        if self._open is None:
            self._open = _OpenBucket(bucket_start=bucket_start)
        elif bucket_start < self._open.bucket_start:
            return None  # late/out-of-order trade for an already-closed window
        elif bucket_start != self._open.bucket_start:
            closed = self._close(self._open)
            self._open = _OpenBucket(bucket_start=bucket_start)

        if trade.side is OrderSide.BUY:
            self._open.buy_volume += trade.quantity
            if trade.quote_quantity is not None:
                self._open.buy_quote_volume += trade.quote_quantity
        else:
            self._open.sell_volume += trade.quantity
        if trade.quote_quantity is None:
            self._open.has_quote_volume = False

        return closed

    def flush(self) -> TakerFlowSnapshot | None:
        """Force-close the current bucket (e.g. on shutdown) and return it."""
        if self._open is None:
            return None
        closed = self._close(self._open)
        self._open = None
        return closed

    def _bucket_start_for(self, timestamp: datetime) -> datetime:
        epoch_seconds = timestamp.timestamp()
        bucket_index = int(epoch_seconds // self._duration_seconds)
        return datetime.fromtimestamp(bucket_index * self._duration_seconds, tz=UTC)

    def _close(self, bucket: _OpenBucket) -> TakerFlowSnapshot:
        return TakerFlowSnapshot(
            symbol=self._symbol,
            contract_type=self._contract_type,
            timeframe=self._timeframe,
            timestamp=bucket.bucket_start,
            buy_volume=bucket.buy_volume,
            sell_volume=bucket.sell_volume,
            buy_quote_volume=bucket.buy_quote_volume if bucket.has_quote_volume else None,
            source=self._source,
        )


__all__ = ["TakerFlowAggregator"]
