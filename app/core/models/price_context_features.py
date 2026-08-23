"""Minimal deterministic price-context feature contract.

Deliberately narrow: return, absolute change, realized trade-price range and
mark-price change only - no moving averages, no RSI/MACD, no
support/resistance. Indicator math belongs to the future ``app.technical``
package, not here. Derived from the same real-time trade/mark-price
observations already retained for taker-flow and funding features, so this
introduces no new fetch.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.feature_status import FeatureStatus


class PriceContextWindowFeatures(DomainModel):
    """Minimal price-context features of one symbol over one lookback window."""

    symbol: Symbol
    contract_type: ContractType
    window: AnalyticsWindow
    window_start: Timestamp
    window_end: Timestamp
    return_pct: Decimal | None = None
    absolute_change: Decimal | None = None
    realized_range: Decimal | None = None
    mark_price_change: Decimal | None = None
    trade_count: int = Field(ge=0)
    status: FeatureStatus
    source: str = Field(min_length=1)
