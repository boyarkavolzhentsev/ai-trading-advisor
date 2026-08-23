"""Deterministic multi-window forced-liquidation feature contract.

Binance liquidation-side semantics (fixed, non-configurable normalization of
a documented exchange convention, not a trading interpretation): the
``forceOrder`` stream's ``side`` is the side of the forced *closing* order
the exchange executed. A forced ``SELL`` closes a long position (counted as
``long_liquidation_volume``); a forced ``BUY`` closes a short position
(counted as ``short_liquidation_volume``). See ``app.flow.liquidation``.

Liquidations are a naturally sparse stream: a window with zero events on a
healthy stream is a legitimate, ``VALID`` zero - never ``UNAVAILABLE``. This
mirrors ``ConnectionHealthTracker``'s own ``judge_by_silence=False`` stance
for this exact stream.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp, Volume
from app.core.models.feature_status import FeatureStatus


class LiquidationWindowFeatures(DomainModel):
    """Forced-liquidation features of one symbol over one lookback window."""

    symbol: Symbol
    contract_type: ContractType
    window: AnalyticsWindow
    window_start: Timestamp
    window_end: Timestamp
    long_liquidation_volume: Volume
    short_liquidation_volume: Volume
    total_liquidation_volume: Volume
    liquidation_imbalance: Decimal
    liquidation_count: int = Field(ge=0)
    liquidation_count_long: int = Field(ge=0)
    liquidation_count_short: int = Field(ge=0)
    average_liquidation_size: Decimal | None = None
    largest_liquidation: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)
