"""Trading cycle configuration contract."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel

PositivePercent = Annotated[Decimal, Field(gt=0, le=100)]


class TradingCycleConfig(DomainModel):
    """Risk and target envelope of one trading cycle.

    The values below are defaults/examples only. Future trading logic must read
    them from a configuration instance - never hard-code them.

    Future rule this contract has to support (not implemented here): at every
    broker/server trading-day rollover the daily risk budget is recalculated
    from *current* account equity, e.g. equity 98,500 with
    ``daily_risk_limit_percent`` 1.5 gives a budget of 1,477.50. Risk-to-stop of
    positions carried into the new day consumes part of that budget. Hence
    ``daily_risk_limit_percent`` is a percentage, not a fixed amount, and the
    equity it applies to is supplied at runtime
    (see ``MoneyManagementDecision``).
    """

    starting_equity: Annotated[Decimal, Field(gt=0)] = Decimal("100000")
    target_profit_percent: PositivePercent = Decimal("6.0")
    daily_risk_limit_percent: PositivePercent = Decimal("1.5")
    per_trade_risk_limit_percent: PositivePercent = Decimal("0.5")
    max_cycle_drawdown_percent: PositivePercent = Decimal("7.5")
    cycle_days: Annotated[int, Field(ge=1)] = 14

    @model_validator(mode="after")
    def _validate_limits(self) -> Self:
        if self.daily_risk_limit_percent > self.max_cycle_drawdown_percent:
            raise ValueError(
                "daily_risk_limit_percent cannot exceed max_cycle_drawdown_percent"
            )
        return self

    @model_validator(mode="after")
    def _validate_per_trade_within_daily(self) -> Self:
        if self.per_trade_risk_limit_percent > self.daily_risk_limit_percent:
            raise ValueError(
                "per_trade_risk_limit_percent cannot exceed daily_risk_limit_percent"
            )
        return self
