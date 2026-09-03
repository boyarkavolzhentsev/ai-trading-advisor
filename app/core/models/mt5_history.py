"""Stage 10D normalized MT5 deal-history output contracts.

``MT5Deal`` is a raw-but-normalized one-``history_deals_get()``-entry
snapshot - no raw MT5 tuple/object/integer constant ever escapes
``app.mt5.client``. ``MT5RealizedDailyPnLAssessment`` is the deterministic,
broker-trading-day aggregation Stage 7's ``AccountRiskSnapshot.
realized_daily_pnl`` will eventually be sourced from - never constructed
here, never fabricated to zero when unsafe.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.models.base import DomainModel, Symbol, Timestamp

_REASON_ORDER: tuple[MT5RealizedPnLBlockReason, ...] = tuple(MT5RealizedPnLBlockReason)


class MT5Deal(DomainModel):
    """Normalized, one-``history_deals_get()``-entry snapshot of one raw MT5
    deal - never a trade recommendation, never an open position.

    ``symbol`` is ``None`` for a ``NON_TRADING`` deal (MT5 reports an empty
    string for account-operation deals). ``profit``/``commission``/``swap``/
    ``fee`` are signed and never clamped/``abs()``-ed - a broker's own sign
    convention is preserved exactly. Deliberately excludes ``reason``
    (``DEAL_REASON_*`` - no V1 use), ``comment``/``magic``/``external_id``
    (no approved project-ownership filtering exists, mirroring
    ``MT5Position``'s identical exclusion).
    """

    ticket: Annotated[int, Field(gt=0)]
    order: Annotated[int, Field(ge=0)]
    position_id: Annotated[int, Field(ge=0)]
    time: Timestamp
    symbol: Symbol | None = None
    deal_type: MT5DealType
    entry: MT5DealEntry
    volume: Annotated[Decimal, Field(ge=0)]
    price: Annotated[Decimal, Field(ge=0)]
    profit: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal


class MT5RealizedDailyPnLAssessment(DomainModel):
    """Deterministic, broker-trading-day aggregation of every qualifying
    deal's contribution to ``realized_daily_pnl``.

    ``READY`` requires every deal considered (see ``app.mt5.history``) to
    have been safely classifiable - including a confirmed-empty qualifying
    set, which legitimately reports exactly ``Decimal("0")``. If ANY deal
    cannot be safely classified, the whole assessment is ``BLOCKED``: no
    partial sum is ever produced, and no unsafe ticket is ever silently
    excluded from ``unsafe_deal_tickets``.
    """

    as_of: Timestamp
    trading_day_key: Annotated[str, Field(min_length=10, max_length=10)]
    outcome: MT5RealizedPnLOutcome
    realized_daily_pnl: Decimal | None = None
    blocked_reasons: tuple[MT5RealizedPnLBlockReason, ...] = ()
    unsafe_deal_tickets: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _validate_trading_day_key_is_iso_date(self) -> Self:
        try:
            date.fromisoformat(self.trading_day_key)
        except ValueError as exc:
            raise ValueError(f"trading_day_key must be a YYYY-MM-DD calendar date: {self.trading_day_key!r}") from exc
        return self

    @model_validator(mode="after")
    def _validate_ready_fields(self) -> Self:
        if self.outcome is MT5RealizedPnLOutcome.READY:
            if self.realized_daily_pnl is None:
                raise ValueError("READY requires realized_daily_pnl")
            if self.blocked_reasons:
                raise ValueError("READY must not carry blocked_reasons")
            if self.unsafe_deal_tickets:
                raise ValueError("READY must not carry unsafe_deal_tickets")
        else:
            if self.realized_daily_pnl is not None:
                raise ValueError("BLOCKED must not carry realized_daily_pnl")
            if not self.blocked_reasons:
                raise ValueError("BLOCKED requires at least one blocked_reason")
            if not self.unsafe_deal_tickets:
                raise ValueError("BLOCKED requires at least one unsafe deal ticket")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.blocked_reasons]
        if indexes != sorted(indexes):
            raise ValueError("blocked_reasons must be in canonical MT5RealizedPnLBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("blocked_reasons must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_unsafe_tickets_unique(self) -> Self:
        if len(set(self.unsafe_deal_tickets)) != len(self.unsafe_deal_tickets):
            raise ValueError("unsafe_deal_tickets must not contain duplicates")
        return self


__all__ = ["MT5Deal", "MT5RealizedDailyPnLAssessment"]
