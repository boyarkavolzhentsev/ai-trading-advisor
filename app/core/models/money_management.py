"""Money management contract."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.models.base import DomainModel, Money, Percent


class MoneyManagementDecision(DomainModel):
    """Sizing envelope for a single new position.

    No sizing arithmetic exists yet. Lot size, margin and leverage stay
    optional until real broker/MT5 instrument data (contract size, min/max lot,
    lot step, tick size, tick value, margin requirement, spread, commission)
    is available.

    Budget fields support the future rollover rule: at every broker trading day
    rollover the daily risk budget is recomputed from current account equity,
    and risk-to-stop of positions carried over consumes part of it.
    ``available_new_risk`` may therefore be negative when carried risk already
    exceeds the fresh budget.
    """

    equity: Money
    daily_risk_budget: Money
    used_open_risk: Money = Decimal("0")
    available_new_risk: Decimal
    recommended_risk_percent: Percent
    recommended_lot: Decimal | None = Field(default=None, ge=0)
    margin_required: Money | None = None
    leverage: Decimal | None = Field(default=None, gt=0)
