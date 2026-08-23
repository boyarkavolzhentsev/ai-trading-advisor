"""Deterministic open-interest calculator.

Open interest has no public WebSocket stream on Binance - every observation
is a REST poll (see
``app.market_data.providers.binance.futures.provider.get_open_interest``).
This module performs **no network I/O and no polling**: it operates purely
over a supplied, already-collected history of ``OpenInterest`` observations.
Never interpolates between polls - every reported value is a real,
previously observed number, always paired with its own age.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.open_interest import OpenInterest
from app.core.models.feature_status import FeatureStatus
from app.core.models.open_interest_features import OpenInterestFeatures, OpenInterestWindowFeatures
from app.flow.quality import stale, unavailable, valid
from app.flow.windows import latest_at_or_before, window_bounds

DEFAULT_MAX_STALENESS = timedelta(minutes=5)


def compute_open_interest_features(
    *,
    symbol: str,
    contract_type: ContractType,
    history: Sequence[OpenInterest],
    windows: Sequence[AnalyticsWindow],
    observation_time: datetime,
    source: str,
    max_staleness: timedelta = DEFAULT_MAX_STALENESS,
) -> OpenInterestFeatures:
    """Compute open-interest change features for every configured window."""
    latest = latest_at_or_before(history, timestamp_of=lambda oi: oi.timestamp, cutoff=observation_time)

    if latest is None:
        return OpenInterestFeatures(
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            status=unavailable("no open interest observation available"),
            source=source,
        )

    staleness_seconds = (observation_time - latest.timestamp).total_seconds()
    is_stale = staleness_seconds > max_staleness.total_seconds()
    freshness_reason = (
        f"latest open interest observation is {staleness_seconds:.3f}s old "
        f"(max {max_staleness.total_seconds()}s)"
        if is_stale
        else None
    )
    top_status = stale(freshness_reason, sample_count=1) if is_stale else valid(1)

    window_features: dict[str, OpenInterestWindowFeatures] = {}
    for window in windows:
        # Both comparison endpoints are the UTC epoch-aligned window boundary
        # (app.flow.windows.window_bounds), not "the current latest value" -
        # so the compared interval is always exactly `window.duration` wide
        # and identical for any observation_time within the same bucket.
        window_start, window_end = window_bounds(observation_time, window.duration)
        end_value = latest_at_or_before(history, timestamp_of=lambda oi: oi.timestamp, cutoff=window_end)
        start_value = latest_at_or_before(history, timestamp_of=lambda oi: oi.timestamp, cutoff=window_start)

        if end_value is None or start_value is None:
            window_features[window.label] = OpenInterestWindowFeatures(
                window=window,
                status=unavailable("no open interest observation at or before window_start/window_end"),
            )
            continue

        absolute_change = end_value.open_interest - start_value.open_interest
        percent_change: Decimal | None
        reasons: list[str] = []
        if start_value.open_interest > 0:
            percent_change = absolute_change / start_value.open_interest * Decimal("100")
        else:
            percent_change = None
            reasons.append("prior open interest is zero; percent_change is undefined")
        oi_velocity = absolute_change / Decimal(str(window.duration.total_seconds()))

        window_features[window.label] = OpenInterestWindowFeatures(
            window=window,
            absolute_change=absolute_change,
            percent_change=percent_change,
            oi_velocity=oi_velocity,
            status=FeatureStatus(
                quality=top_status.quality,
                sample_count=2 if start_value is not end_value else 1,
                reasons=reasons,
            ),
        )

    return OpenInterestFeatures(
        symbol=symbol,
        contract_type=contract_type,
        observation_time=observation_time,
        latest_open_interest=latest.open_interest,
        latest_observed_at=latest.timestamp,
        staleness_seconds=staleness_seconds,
        windows=window_features,
        status=top_status,
        source=source,
    )


__all__ = ["DEFAULT_MAX_STALENESS", "compute_open_interest_features"]
