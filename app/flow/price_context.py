"""Minimal deterministic price-context calculator.

Deliberately narrow: return, absolute change and realized trade-price range
from a supplied ``TradeEvent`` history, plus mark-price change from a
supplied ``FundingRate`` history - no moving averages, no RSI/MACD, no
support/resistance. Both histories are the same real-time observations
already retained for taker-flow and funding features; this introduces no
new fetch.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.funding import FundingRate
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.core.models.trade_event import TradeEvent
from app.flow.quality import partial, unavailable, valid
from app.flow.windows import latest_at_or_before, select_window, validate_unique_labels, window_bounds

MIN_TRADES_FOR_RETURN = 2


def compute_price_context_features(
    *,
    symbol: str,
    contract_type: ContractType,
    trades: Sequence[TradeEvent],
    mark_prices: Sequence[FundingRate],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
) -> dict[str, PriceContextWindowFeatures]:
    """Compute minimal price-context features for every configured window."""
    validate_unique_labels(windows)

    result: dict[str, PriceContextWindowFeatures] = {}
    for window in windows:
        window_start, window_end = window_bounds(observation_time, window.duration)
        window_trades = sorted(
            select_window(
                trades, timestamp_of=lambda t: t.timestamp, observation_time=observation_time, duration=window.duration
            ),
            key=lambda t: t.timestamp,
        )
        trade_count = len(window_trades)

        return_pct = None
        absolute_change = None
        realized_range = None
        if trade_count >= MIN_TRADES_FOR_RETURN:
            first, last = window_trades[0], window_trades[-1]
            absolute_change = last.price - first.price
            if first.price > 0:
                return_pct = absolute_change / first.price * 100
            prices = [trade.price for trade in window_trades]
            realized_range = max(prices) - min(prices)
        elif trade_count == 1:
            realized_range = window_trades[0].price - window_trades[0].price  # a single print: zero range, a real fact

        # Both endpoints are the UTC epoch-aligned window boundary, not
        # "current" vs "window_start ago" - keeps the compared interval
        # exactly window.duration wide and reproducible within a bucket.
        end_mark = latest_at_or_before(mark_prices, timestamp_of=lambda f: f.timestamp, cutoff=window_end)
        start_mark = latest_at_or_before(mark_prices, timestamp_of=lambda f: f.timestamp, cutoff=window_start)
        mark_price_change = (
            end_mark.mark_price - start_mark.mark_price
            if end_mark is not None and start_mark is not None
            else None
        )

        if trade_count == 0:
            status = unavailable("no trades in window")
        elif trade_count < MIN_TRADES_FOR_RETURN:
            status = partial("fewer than 2 trades in window; return/absolute_change undefined", sample_count=trade_count)
        else:
            status = valid(trade_count)

        result[window.label] = PriceContextWindowFeatures(
            symbol=symbol,
            contract_type=contract_type,
            window=window,
            window_start=window_start,
            window_end=window_end,
            return_pct=return_pct,
            absolute_change=absolute_change,
            realized_range=realized_range,
            mark_price_change=mark_price_change,
            trade_count=trade_count,
            status=status,
            source=source,
        )
    return result


__all__ = ["compute_price_context_features"]
