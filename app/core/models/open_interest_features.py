"""Deterministic open-interest feature contract.

Open interest has no public WebSocket stream on Binance - every observation
is a REST poll (see ``app.market_data.providers.binance.futures.provider``).
This model never interpolates between polls: ``latest_open_interest`` is
always a real, previously-observed value, and ``staleness_seconds`` always
makes its age explicit rather than silently treating it as fresh.
``percent_change``/``oi_velocity`` are signed and unrelated to the
non-negative ``Percent`` alias used elsewhere in the codebase for
account-risk percentages.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp, Volume
from app.core.models.feature_status import FeatureStatus


class OpenInterestWindowFeatures(DomainModel):
    """Open-interest change features of one symbol over one lookback window."""

    window: AnalyticsWindow
    absolute_change: Decimal | None = None
    percent_change: Decimal | None = None
    oi_velocity: Decimal | None = None
    status: FeatureStatus


class OpenInterestFeatures(DomainModel):
    """Open-interest features of one symbol, derived from a supplied history."""

    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp
    latest_open_interest: Volume | None = None
    latest_observed_at: Timestamp | None = None
    staleness_seconds: float | None = None
    windows: dict[str, OpenInterestWindowFeatures] = Field(default_factory=dict)
    status: FeatureStatus
    source: str = Field(min_length=1)
