"""Deterministic multi-window forced-liquidation calculator.

Binance liquidation-side semantics (fixed, non-configurable normalization of
a documented exchange convention, not a trading interpretation): the
``forceOrder`` stream's ``side`` is the side of the forced *closing* order
the exchange executed. A forced ``SELL`` closes a long position (counted as
long-liquidation volume); a forced ``BUY`` closes a short position (counted
as short-liquidation volume).

Liquidations are a naturally sparse stream: a window with zero events on a
healthy stream is a legitimate ``VALID`` zero, never ``UNAVAILABLE`` -
mirrors ``ConnectionHealthTracker``'s ``judge_by_silence=False`` stance for
this exact stream. Cluster/burst detection is deliberately not implemented:
it requires a subjective threshold this deterministic layer does not pick.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.liquidation import LiquidationEvent
from app.core.models.liquidation_features import LiquidationWindowFeatures
from app.flow.quality import partial, truncation_reason, valid
from app.flow.windows import select_window, validate_unique_labels, window_bounds


def compute_liquidation_features(
    *,
    symbol: str,
    contract_type: ContractType,
    liquidations: Sequence[LiquidationEvent],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
    dropped_count: int = 0,
) -> dict[str, LiquidationWindowFeatures]:
    """Compute liquidation-flow features for every configured window."""
    validate_unique_labels(windows)

    relevant = [event for event in liquidations if event.timestamp <= observation_time]
    earliest_retained = min((event.timestamp for event in liquidations), default=None)

    result: dict[str, LiquidationWindowFeatures] = {}
    for window in windows:
        window_start, window_end = window_bounds(observation_time, window.duration)
        window_events = select_window(
            relevant,
            timestamp_of=lambda event: event.timestamp,
            observation_time=observation_time,
            duration=window.duration,
        )

        long_events = [event for event in window_events if event.side is OrderSide.SELL]
        short_events = [event for event in window_events if event.side is OrderSide.BUY]
        long_volume = sum((event.quantity for event in long_events), start=Decimal("0"))
        short_volume = sum((event.quantity for event in short_events), start=Decimal("0"))
        total_volume = long_volume + short_volume
        count = len(window_events)
        quantities = [event.quantity for event in window_events]

        status = valid(count)
        reason = truncation_reason(
            window_start=window_start, earliest_retained=earliest_retained, dropped_count=dropped_count
        )
        if reason:
            status = partial(reason, sample_count=count)

        result[window.label] = LiquidationWindowFeatures(
            symbol=symbol,
            contract_type=contract_type,
            window=window,
            window_start=window_start,
            window_end=window_end,
            long_liquidation_volume=long_volume,
            short_liquidation_volume=short_volume,
            total_liquidation_volume=total_volume,
            liquidation_imbalance=long_volume - short_volume,
            liquidation_count=count,
            liquidation_count_long=len(long_events),
            liquidation_count_short=len(short_events),
            average_liquidation_size=(total_volume / count) if count > 0 else None,
            largest_liquidation=max(quantities) if quantities else None,
            status=status,
            source=source,
        )
    return result


__all__ = ["compute_liquidation_features"]
