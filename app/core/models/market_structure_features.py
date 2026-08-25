"""Deterministic Stage 3A market-structure contract: confirmed fractal
swings and objective, close-based structural breaks.

No "market structure regime", no BOS/CHoCH vocabulary, no bullish/bearish
label - ``SwingPoint``/``StructuralBreak`` are geometric facts only.
Confirmation semantics are load-bearing: a ``SwingPoint`` never exists
before its ``confirmed_at`` (strictly after ``candle_time``), and a
``StructuralBreak`` never exists before its broken swing's own
``confirmed_at`` - both enforced structurally here, not just by convention
in the calculator.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.feature_status import FeatureStatus


class SwingPoint(DomainModel):
    """One confirmed N-left/N-right fractal swing extreme."""

    kind: SwingKind
    candle_time: Timestamp
    price: Price
    confirmed_at: Timestamp
    left_bars: int = Field(ge=1)
    right_bars: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_confirmation_order(self) -> Self:
        if self.confirmed_at <= self.candle_time:
            raise ValueError("confirmed_at must be strictly after candle_time")
        return self


class StructuralBreak(DomainModel):
    """One objective, close-based break of an already-confirmed swing."""

    direction: BreakDirection
    broken_swing: SwingPoint
    break_candle_time: Timestamp
    break_close: Price
    confirmed_at: Timestamp

    @model_validator(mode="after")
    def _validate_break_after_confirmation(self) -> Self:
        if self.break_candle_time <= self.broken_swing.confirmed_at:
            raise ValueError("break_candle_time must be strictly after the broken swing's confirmed_at")
        if self.confirmed_at != self.break_candle_time:
            raise ValueError("confirmed_at must equal break_candle_time - a break needs no additional lag")
        return self


class MarketStructureFeatures(DomainModel):
    """Confirmed swings and structural breaks of one symbol/timeframe."""

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    left_bars: int = Field(ge=1)
    right_bars: int = Field(ge=1)
    swings: tuple[SwingPoint, ...] = Field(default_factory=tuple)
    breaks: tuple[StructuralBreak, ...] = Field(default_factory=tuple)
    status: FeatureStatus
    source: str = Field(min_length=1)


__all__ = ["MarketStructureFeatures", "StructuralBreak", "SwingPoint"]
