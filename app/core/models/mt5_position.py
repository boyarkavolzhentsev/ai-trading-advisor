"""Stage 10C existing-open-position normalization and account-wide open-risk
output contracts.

``MT5Position`` is a raw-but-normalized one-``positions_get()``-entry
snapshot - no raw MT5 tuple/object/integer constant ever escapes
``app.mt5.client``. ``MT5OpenRiskAssessment`` is the deterministic,
account-wide aggregation Stage 7's ``AccountRiskSnapshot.
current_open_risk_to_stop`` will eventually be sourced from - never
constructed here, never fabricated to zero when unsafe.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_position import MT5OpenRiskBlockReason, MT5OpenRiskOutcome
from app.core.enums.order import OrderSide
from app.core.models.base import DomainModel, Price, Symbol, Timestamp

_REASON_ORDER: tuple[MT5OpenRiskBlockReason, ...] = tuple(MT5OpenRiskBlockReason)


class MT5Position(DomainModel):
    """Normalized, one-``positions_get()``-entry snapshot of an existing
    open position - never a trade recommendation.

    ``price_open`` is structurally guaranteed by MT5 for any real open
    position (a fixed historical fill price, never a live-updating fact) -
    construction-rejected if non-positive, unlike ``price_current`` (a live
    quote that can legitimately be a business-rule concern rather than a
    construction error - see ``app.mt5.risk``). ``stop_loss`` is ``None``
    when MT5 reports the ``sl == 0.0`` "no stop" sentinel - never a
    fabricated zero price. Deliberately excludes ``price_open`` derivatives
    like ``profit``/``swap`` (already reflected account-level in Stage 10B's
    ``MT5AccountFacts.floating_pnl``), ``tp`` (irrelevant to downside
    risk-to-stop), ``magic``/``comment`` (no approved project-ownership
    filtering exists), and ``time``/``time_msc`` (no V1 use).
    """

    as_of: Timestamp
    ticket: Annotated[int, Field(gt=0)]
    symbol: Symbol
    side: OrderSide
    volume: Annotated[Decimal, Field(gt=0)]
    price_open: Annotated[Decimal, Field(gt=0)]
    price_current: Price
    stop_loss: Price | None = None


class MT5OpenRiskAssessment(DomainModel):
    """Deterministic, account-wide aggregation of every open position's
    contribution to ``current_open_risk_to_stop``.

    ``READY`` requires every open position to have been safely assessable -
    including positions that are protected under the entry/stop
    classification and so contribute exactly ``0``. If ANY position cannot
    be safely assessed, the whole assessment is ``BLOCKED``: no partial sum
    is ever produced, and no unsafe ticket is ever silently excluded from
    ``unsafe_tickets``.
    """

    as_of: Timestamp
    outcome: MT5OpenRiskOutcome
    current_open_risk_to_stop: Annotated[Decimal, Field(ge=0)] | None = None
    blocked_reasons: tuple[MT5OpenRiskBlockReason, ...] = ()
    unsafe_tickets: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _validate_ready_fields(self) -> Self:
        if self.outcome is MT5OpenRiskOutcome.READY:
            if self.current_open_risk_to_stop is None:
                raise ValueError("READY requires current_open_risk_to_stop")
            if self.blocked_reasons:
                raise ValueError("READY must not carry blocked_reasons")
            if self.unsafe_tickets:
                raise ValueError("READY must not carry unsafe_tickets")
        else:
            if self.current_open_risk_to_stop is not None:
                raise ValueError("BLOCKED must not carry current_open_risk_to_stop")
            if not self.blocked_reasons:
                raise ValueError("BLOCKED requires at least one blocked_reason")
            if not self.unsafe_tickets:
                raise ValueError("BLOCKED requires at least one unsafe ticket")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.blocked_reasons]
        if indexes != sorted(indexes):
            raise ValueError("blocked_reasons must be in canonical MT5OpenRiskBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("blocked_reasons must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_unsafe_tickets_unique(self) -> Self:
        if len(set(self.unsafe_tickets)) != len(self.unsafe_tickets):
            raise ValueError("unsafe_tickets must not contain duplicates")
        return self


__all__ = ["MT5OpenRiskAssessment", "MT5Position"]
