"""Deterministic multi-window taker buy/sell flow feature contract.

Computed over a supplied history of raw ``TradeEvent``s - never over
``TakerFlowSnapshot`` buckets, so there is exactly one source of truth for
"which trades are in this window" (see ``app.flow.taker_flow``).
``buy_ratio``/``sell_ratio`` are ``None`` when the window has no volume at
all - a window with zero trades is ``UNAVAILABLE``, never a fabricated
``0.0`` ratio (unlike ``TakerFlowSnapshot.buy_ratio``, whose ``0.0`` default
suits its narrower, single-bucket REST/streaming use case, not this
feature layer's ZERO-vs-UNKNOWN requirement).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp, Volume
from app.core.models.feature_status import FeatureStatus


class TakerFlowWindowFeatures(DomainModel):
    """Taker buy/sell flow features of one symbol over one lookback window."""

    symbol: Symbol
    contract_type: ContractType
    window: AnalyticsWindow
    window_start: Timestamp
    window_end: Timestamp
    buy_volume: Volume
    sell_volume: Volume
    total_volume: Volume
    delta: Decimal
    buy_ratio: float | None = None
    sell_ratio: float | None = None
    delta_rate: Decimal
    cumulative_delta: Decimal
    cumulative_delta_since: Timestamp | None = None
    trade_count: int = Field(ge=0)
    status: FeatureStatus
    source: str = Field(min_length=1)
