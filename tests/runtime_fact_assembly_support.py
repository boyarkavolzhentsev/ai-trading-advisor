"""Shared builders for Runtime Fact Assembly tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.mt5_history import MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.enums.mt5_position import MT5OpenRiskBlockReason, MT5OpenRiskOutcome
from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode, MT5RolloverOutcome
from app.core.models.mt5_history import MT5RealizedDailyPnLAssessment
from app.core.models.mt5_position import MT5OpenRiskAssessment
from app.core.models.mt5_rollover import MT5RolloverSnapshot, MT5RolloverState

__all__ = [
    "AS_OF",
    "TRADING_DAY_KEY",
    "blocked_open_risk",
    "blocked_realized_pnl",
    "rollover_bootstrapped_midday",
    "rollover_ready",
    "rollover_unusable",
    "usable_open_risk",
    "usable_realized_pnl",
]

AS_OF = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
TRADING_DAY_KEY = "2026-01-01"


def _rollover_state(
    *,
    trading_day_key: str = TRADING_DAY_KEY,
    rollover_equity: Decimal = Decimal("100000"),
    establishment_mode: MT5RolloverEstablishmentMode = MT5RolloverEstablishmentMode.POST_BOUNDARY_FIRST_OBSERVATION,
) -> MT5RolloverState:
    return MT5RolloverState(
        trading_day_key=trading_day_key,
        rollover_equity=rollover_equity,
        established_at=AS_OF,
        rollover_timezone="UTC",
        rollover_hour=0,
        establishment_mode=establishment_mode,
    )


def rollover_ready(
    *,
    as_of: datetime = AS_OF,
    rollover_equity: Decimal = Decimal("100000"),
    current_equity: Decimal = Decimal("101000"),
    floating_pnl: Decimal = Decimal("-50"),
    trading_day_key: str = TRADING_DAY_KEY,
) -> MT5RolloverSnapshot:
    return MT5RolloverSnapshot(
        as_of=as_of,
        rollover_outcome=MT5RolloverOutcome.READY,
        rollover_state=_rollover_state(trading_day_key=trading_day_key, rollover_equity=rollover_equity),
        current_equity=current_equity,
        floating_pnl=floating_pnl,
    )


def rollover_bootstrapped_midday(
    *, as_of: datetime = AS_OF, rollover_equity: Decimal = Decimal("100000"), trading_day_key: str = TRADING_DAY_KEY
) -> MT5RolloverSnapshot:
    return MT5RolloverSnapshot(
        as_of=as_of,
        rollover_outcome=MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY,
        rollover_state=_rollover_state(
            trading_day_key=trading_day_key, rollover_equity=rollover_equity, establishment_mode=MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP
        ),
        current_equity=Decimal("101000"),
        floating_pnl=Decimal("0"),
    )


def rollover_unusable(*, outcome: MT5RolloverOutcome, as_of: datetime = AS_OF) -> MT5RolloverSnapshot:
    return MT5RolloverSnapshot(as_of=as_of, rollover_outcome=outcome, rollover_state=None, current_equity=Decimal("101000"), floating_pnl=Decimal("0"))


def usable_realized_pnl(
    *, as_of: datetime = AS_OF, realized_daily_pnl: Decimal = Decimal("200"), trading_day_key: str = TRADING_DAY_KEY
) -> MT5RealizedDailyPnLAssessment:
    return MT5RealizedDailyPnLAssessment(
        as_of=as_of, trading_day_key=trading_day_key, outcome=MT5RealizedPnLOutcome.READY, realized_daily_pnl=realized_daily_pnl
    )


def blocked_realized_pnl(*, as_of: datetime = AS_OF, trading_day_key: str = TRADING_DAY_KEY) -> MT5RealizedDailyPnLAssessment:
    return MT5RealizedDailyPnLAssessment(
        as_of=as_of,
        trading_day_key=trading_day_key,
        outcome=MT5RealizedPnLOutcome.BLOCKED,
        blocked_reasons=(MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP,),
        unsafe_deal_tickets=(1,),
    )


def usable_open_risk(*, as_of: datetime = AS_OF, current_open_risk_to_stop: Decimal = Decimal("300")) -> MT5OpenRiskAssessment:
    return MT5OpenRiskAssessment(as_of=as_of, outcome=MT5OpenRiskOutcome.READY, current_open_risk_to_stop=current_open_risk_to_stop)


def blocked_open_risk(*, as_of: datetime = AS_OF) -> MT5OpenRiskAssessment:
    return MT5OpenRiskAssessment(
        as_of=as_of, outcome=MT5OpenRiskOutcome.BLOCKED, blocked_reasons=(MT5OpenRiskBlockReason.NO_PROTECTIVE_STOP,), unsafe_tickets=(1001,)
    )
