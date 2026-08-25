"""Deterministic Stage 3A candle-geometry contract.

Pure geometric facts about the single most recent CLOSED candle - no named
candlestick patterns (no "hammer", no "engulfing"), no reversal/continuation
interpretation. ``body_to_range_ratio``/``close_location_value`` are
``None`` (never a fabricated ``0``) whenever ``range_size`` is exactly
zero, since the ratio is genuinely undefined in that case.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.feature_status import FeatureStatus


class CandleStructureFeatures(DomainModel):
    """Geometric facts of the most recent closed candle."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    candle_time: Timestamp | None = None
    body_size: Decimal | None = None
    upper_wick: Decimal | None = None
    lower_wick: Decimal | None = None
    range_size: Decimal | None = None
    body_to_range_ratio: Decimal | None = None
    close_location_value: Decimal | None = None
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["CandleStructureFeatures"]
