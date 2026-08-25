"""Bounded per-(symbol, contract_type, timeframe) history backing Stage 3A.

Candle retention uses ``app.technical.candle_store.ChronologicalCandleStore``
- deterministic by candle timestamp, not drop-oldest-by-insertion-order like
``app.market_data.realtime.buffers.BoundedBuffer`` (correct for Stage 1/2's
real-time streams, but wrong here since Stage 3A candle batches may arrive
out of order). Only candle retention gets this treatment: the derived-
snapshot history below still uses ``BoundedBuffer`` unchanged, since
snapshots are produced by the engine itself strictly in build order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.market_data.realtime.buffers import BoundedBuffer
from app.technical.candle_store import ChronologicalCandleStore

DEFAULT_CANDLE_CAPACITY = 1000
DEFAULT_SNAPSHOT_CAPACITY = 200


@dataclass(slots=True)
class SymbolTimeframeHistory:
    """Bounded candle and snapshot history of one ``(symbol, contract_type, timeframe)``.

    ``candle_capacity`` should be sized to comfortably exceed the largest
    configured lookback/period any calculator in this package uses (e.g.
    the widest moving-average period).
    """

    candles: ChronologicalCandleStore
    snapshots: BoundedBuffer[TechnicalFeatureSnapshot]

    @classmethod
    def with_capacity(
        cls,
        *,
        candle_capacity: int = DEFAULT_CANDLE_CAPACITY,
        snapshot_capacity: int = DEFAULT_SNAPSHOT_CAPACITY,
    ) -> Self:
        return cls(
            candles=ChronologicalCandleStore(capacity=candle_capacity),
            snapshots=BoundedBuffer(maxlen=snapshot_capacity),
        )


__all__ = ["DEFAULT_CANDLE_CAPACITY", "DEFAULT_SNAPSHOT_CAPACITY", "SymbolTimeframeHistory"]
