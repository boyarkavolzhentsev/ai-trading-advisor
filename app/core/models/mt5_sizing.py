"""Stage 10C broker-aware final candidate sizing input/output contracts.

``MT5BrokerSizingRequest`` is shaped after ``CandidateRiskInput`` (Stage 7's
own precedent for "the one external fact this stage cannot derive itself,
supplied explicitly by the caller"): ``TradeSetup`` is not wired into the
Router/Judge/Policy/Risk/Portfolio/Session chain anywhere in this repository,
so Stage 10C declares its own narrow, explicit input contract rather than
inventing a connection to a model nothing upstream produces.

Converts one already-approved ``session_allocated_risk`` (Stage 9's own
output, authoritative - never Stage 7's stale ``recommended_units``) into an
actionable, broker-normalized volume. Never applies a protected-profit
concept (that only applies to an already-open position with a real entry
fill, never a not-yet-opened candidate) and never nets against existing
positions (see ``app.mt5.sizing``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.trade import TradeDirection
from app.core.models.base import DomainModel, Price, Symbol, Timestamp


class MT5BrokerSizingRequest(DomainModel):
    """One new candidate's broker-aware sizing request.

    ``entry_price``, when supplied, is always authoritative and no live
    quote is consulted; when absent, the live quote is used
    direction-appropriately (``ask`` for LONG, ``bid`` for SHORT) - the two
    sources are never mixed within one calculation (see ``app.mt5.sizing``).
    """

    symbol: Symbol
    direction: TradeDirection
    stop_loss: Price
    entry_price: Price | None = None
    session_allocated_risk: Annotated[Decimal, Field(gt=0)]

    @model_validator(mode="after")
    def _validate_direction_is_actionable(self) -> Self:
        if self.direction not in (TradeDirection.LONG, TradeDirection.SHORT):
            raise ValueError("sizing request requires LONG or SHORT direction")
        return self


class MT5BrokerSizingResult(DomainModel):
    """Result of one broker-aware final sizing calculation.

    ``broker_volume``/``actual_monetary_risk`` are present if and only if
    ``outcome`` is ``ACTIONABLE`` - every other outcome fails closed with
    neither populated, never a partial/best-effort sizing result.
    """

    as_of: Timestamp
    outcome: MT5SizingOutcome
    broker_volume: Annotated[Decimal, Field(gt=0)] | None = None
    actual_monetary_risk: Annotated[Decimal, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def _validate_actionable_fields(self) -> Self:
        if self.outcome is MT5SizingOutcome.ACTIONABLE:
            if self.broker_volume is None:
                raise ValueError("ACTIONABLE requires broker_volume")
            if self.actual_monetary_risk is None:
                raise ValueError("ACTIONABLE requires actual_monetary_risk")
        else:
            if self.broker_volume is not None:
                raise ValueError("non-ACTIONABLE outcome must not carry broker_volume")
            if self.actual_monetary_risk is not None:
                raise ValueError("non-ACTIONABLE outcome must not carry actual_monetary_risk")
        return self


__all__ = ["MT5BrokerSizingRequest", "MT5BrokerSizingResult"]
