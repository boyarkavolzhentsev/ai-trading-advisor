"""Deterministic multi-window taker buy/sell flow calculator.

Operates directly over a supplied history of raw ``TradeEvent``s - never
over pre-aggregated ``TakerFlowSnapshot`` buckets - so there is exactly one
source of truth for "which trades fall in this window" (``app.flow.windows``
's trailing-window rule). Pure function: no I/O, no state, no
interpretation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.taker_flow_features import TakerFlowWindowFeatures
from app.core.models.trade_event import TradeEvent
from app.flow.quality import partial, truncation_reason, unavailable, valid
from app.flow.windows import select_window, validate_unique_labels, window_bounds


def compute_taker_flow_features(
    *,
    symbol: str,
    contract_type: ContractType,
    trades: Sequence[TradeEvent],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
    dropped_count: int = 0,
) -> dict[str, TakerFlowWindowFeatures]:
    """Compute taker-flow features for every configured window.

    ``dropped_count`` is the retaining ``BoundedBuffer``'s eviction count
    (``0`` if the caller does not track it); it is used only to flag a
    window as ``PARTIAL`` when eviction may have truncated it.
    """
    validate_unique_labels(windows)

    relevant = [trade for trade in trades if trade.timestamp <= observation_time]
    earliest_retained = min((trade.timestamp for trade in trades), default=None)

    cumulative_delta = sum(
        (trade.quantity if trade.side is OrderSide.BUY else -trade.quantity for trade in relevant),
        start=Decimal("0"),
    )
    cumulative_delta_since = min((trade.timestamp for trade in relevant), default=None)

    result: dict[str, TakerFlowWindowFeatures] = {}
    for window in windows:
        window_start, window_end = window_bounds(observation_time, window.duration)
        window_trades = select_window(
            relevant,
            timestamp_of=lambda trade: trade.timestamp,
            observation_time=observation_time,
            duration=window.duration,
        )
        trade_count = len(window_trades)
        buy_volume = sum(
            (trade.quantity for trade in window_trades if trade.side is OrderSide.BUY),
            start=Decimal("0"),
        )
        sell_volume = sum(
            (trade.quantity for trade in window_trades if trade.side is OrderSide.SELL),
            start=Decimal("0"),
        )
        total_volume = buy_volume + sell_volume
        delta = buy_volume - sell_volume
        buy_ratio = float(buy_volume / total_volume) if total_volume > 0 else None
        sell_ratio = (1.0 - buy_ratio) if buy_ratio is not None else None
        delta_rate = delta / Decimal(str(window.duration.total_seconds()))

        if trade_count == 0:
            status = unavailable("no trades in window")
        else:
            reason = truncation_reason(
                window_start=window_start, earliest_retained=earliest_retained, dropped_count=dropped_count
            )
            status = partial(reason, sample_count=trade_count) if reason else valid(trade_count)

        result[window.label] = TakerFlowWindowFeatures(
            symbol=symbol,
            contract_type=contract_type,
            window=window,
            window_start=window_start,
            window_end=window_end,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            total_volume=total_volume,
            delta=delta,
            buy_ratio=buy_ratio,
            sell_ratio=sell_ratio,
            delta_rate=delta_rate,
            cumulative_delta=cumulative_delta,
            cumulative_delta_since=cumulative_delta_since,
            trade_count=trade_count,
            status=status,
            source=source,
        )
    return result


__all__ = ["compute_taker_flow_features"]
