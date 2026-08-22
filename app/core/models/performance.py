"""Performance statistics contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.models.base import DomainModel, Ratio

Count = Annotated[int, Field(ge=0)]


class PerformanceSnapshot(DomainModel):
    """Aggregated performance figures.

    Pure data container: no statistics are computed in this stage. Derived
    metrics are optional because they are undefined for an empty or partial
    sample (e.g. profit factor with zero losses).
    """

    total_trades: Count = 0
    wins: Count = 0
    losses: Count = 0
    breakeven: Count = 0
    not_filled: Count = 0
    expired: Count = 0
    win_rate: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    profit_factor: Ratio | None = None
    expectancy: Decimal | None = None
    max_drawdown: Annotated[Decimal, Field(ge=0)] | None = None
