"""Deterministic funding-rate calculator.

Operates over a supplied history of ``FundingRate`` observations - unlike
open interest, the mark-price WebSocket stream already delivers these
continuously (``app.market_data.providers.binance.futures.realtime.provider``),
so this module needs no polling. ``time_to_next_funding`` is ``None``
whenever the venue does not disclose ``next_funding_time``: the funding
interval is never assumed to be any particular duration.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.feature_status import FeatureStatus
from app.core.models.funding import FundingRate
from app.core.models.funding_features import FundingFeatures, FundingWindowFeatures
from app.flow.quality import stale, unavailable, valid, worse_of
from app.flow.windows import latest_at_or_before, select_window, window_bounds

DEFAULT_MAX_STALENESS = timedelta(minutes=5)
MIN_SAMPLES_FOR_STDDEV = 2

_BPS_DIVISOR = Decimal("10000")


def compute_funding_features(
    *,
    symbol: str,
    contract_type: ContractType,
    history: Sequence[FundingRate],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
    max_staleness: timedelta = DEFAULT_MAX_STALENESS,
) -> FundingFeatures:
    """Compute funding-rate trend/statistics features for every configured window."""
    latest = latest_at_or_before(history, timestamp_of=lambda f: f.timestamp, cutoff=observation_time)

    if latest is None:
        return FundingFeatures(
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            status=unavailable("no funding rate observation available"),
            source=source,
        )

    mark_index_basis = latest.mark_price - latest.index_price
    mark_index_basis_bps = (
        mark_index_basis / latest.index_price * _BPS_DIVISOR if latest.index_price > 0 else None
    )
    time_to_next_funding = (
        latest.next_funding_time - observation_time if latest.next_funding_time is not None else None
    )

    staleness_seconds = (observation_time - latest.timestamp).total_seconds()
    is_stale = staleness_seconds > max_staleness.total_seconds()
    freshness_reason = (
        f"latest funding observation is {staleness_seconds:.3f}s old (max {max_staleness.total_seconds()}s)"
        if is_stale
        else None
    )
    top_status = stale(freshness_reason, sample_count=1) if is_stale else valid(1)

    window_features: dict[str, FundingWindowFeatures] = {}
    for window in windows:
        window_events = select_window(
            history, timestamp_of=lambda f: f.timestamp, observation_time=observation_time, duration=window.duration
        )
        sample_count = len(window_events)
        # funding_trend compares the two UTC epoch-aligned window endpoints
        # (not "current" vs "window_start ago"), so it is exactly
        # window.duration wide and reproducible for any observation_time
        # within the same aligned bucket.
        window_start, window_end = window_bounds(observation_time, window.duration)
        end_value = latest_at_or_before(history, timestamp_of=lambda f: f.timestamp, cutoff=window_end)
        start_value = latest_at_or_before(history, timestamp_of=lambda f: f.timestamp, cutoff=window_start)
        funding_trend = (
            end_value.funding_rate - start_value.funding_rate
            if end_value is not None and start_value is not None
            else None
        )

        rates = [event.funding_rate for event in window_events]
        rolling_mean = statistics.mean(rates) if rates else None
        rolling_stddev = statistics.pstdev(rates) if len(rates) >= MIN_SAMPLES_FOR_STDDEV else None

        if sample_count == 0 and start_value is None and end_value is None:
            status = unavailable("no funding observations in or before window")
        elif sample_count < MIN_SAMPLES_FOR_STDDEV:
            status = FeatureStatus(
                quality=worse_of(FeatureQuality.PARTIAL, top_status.quality),
                sample_count=sample_count,
                reasons=["fewer than 2 observations in window; rolling_stddev is undefined"],
            )
        else:
            status = FeatureStatus(quality=top_status.quality, sample_count=sample_count)

        window_features[window.label] = FundingWindowFeatures(
            window=window,
            funding_trend=funding_trend,
            rolling_mean=rolling_mean,
            rolling_stddev=rolling_stddev,
            sample_count=sample_count,
            status=status,
        )

    return FundingFeatures(
        symbol=symbol,
        contract_type=contract_type,
        observation_time=observation_time,
        latest_funding_rate=latest.funding_rate,
        latest_mark_price=latest.mark_price,
        latest_index_price=latest.index_price,
        latest_observed_at=latest.timestamp,
        mark_index_basis=mark_index_basis,
        mark_index_basis_bps=mark_index_basis_bps,
        time_to_next_funding=time_to_next_funding,
        windows=window_features,
        status=top_status,
        source=source,
    )


__all__ = ["DEFAULT_MAX_STALENESS", "compute_funding_features"]
