"""Deterministic funding-rate feature contract.

Derived from a supplied history of ``FundingRate`` observations - the
mark-price WebSocket stream already delivers these continuously (see
``app.market_data.providers.binance.futures.realtime.provider``), so unlike
open interest this is not a slow REST-only source. ``time_to_next_funding``
is ``None`` whenever the venue does not disclose ``next_funding_time``; the
funding interval is never assumed to be any particular duration (never
hard-coded to 8 hours), matching ``FundingRate.funding_interval_hours``'s
own ``None``-means-undisclosed convention.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.feature_status import FeatureStatus


class FundingWindowFeatures(DomainModel):
    """Funding-rate trend/statistics of one symbol over one lookback window."""

    window: AnalyticsWindow
    funding_trend: Decimal | None = None
    rolling_mean: Decimal | None = None
    rolling_stddev: Decimal | None = None
    sample_count: int = Field(ge=0, default=0)
    status: FeatureStatus


class FundingFeatures(DomainModel):
    """Funding/mark-price features of one symbol, derived from a supplied history."""

    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp
    latest_funding_rate: Decimal | None = None
    latest_mark_price: Price | None = None
    latest_index_price: Price | None = None
    latest_observed_at: Timestamp | None = None
    mark_index_basis: Decimal | None = None
    mark_index_basis_bps: Decimal | None = None
    time_to_next_funding: timedelta | None = None
    windows: dict[str, FundingWindowFeatures] = Field(default_factory=dict)
    status: FeatureStatus
    source: str = Field(min_length=1)
