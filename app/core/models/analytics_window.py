"""Configurable flow-analytics window value object.

Deliberately distinct from ``Timeframe`` (``app.core.enums.market``):
``Timeframe`` is bound to candle-interval provider mapping
(``app.market_data.timeframes``) and has no sub-minute members, while an
``AnalyticsWindow`` is a free-form duration used purely for flow-feature
aggregation (e.g. 10s/30s have no Binance kline interval and no candle
staleness meaning). Calculators accept a ``Sequence[AnalyticsWindow]`` and
never hard-code a window inside their own logic.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel


class AnalyticsWindow(DomainModel):
    """One named, positive-duration lookback window."""

    label: str = Field(min_length=1)
    duration: timedelta

    @model_validator(mode="after")
    def _validate_duration(self) -> Self:
        if self.duration <= timedelta(0):
            raise ValueError("duration must be positive")
        return self
