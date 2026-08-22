"""Technical picture contract."""

from __future__ import annotations

from pydantic import Field

from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Price, Symbol, Timestamp


class TechnicalSnapshot(DomainModel):
    """Deterministically derived technical picture for one symbol/timeframe.

    Intentionally generic: qualitative descriptors are plain strings for now so
    that future calculators can define their own vocabularies without a
    breaking contract change. Indicator values are not modelled yet.
    """

    symbol: Symbol
    timeframe: Timeframe
    timestamp: Timestamp
    trend: str | None = None
    momentum: str | None = None
    volatility: str | None = None
    support_levels: list[Price] = Field(default_factory=list)
    resistance_levels: list[Price] = Field(default_factory=list)
    market_structure: str | None = None
