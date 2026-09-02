"""Stage 10B rollover-state and account-snapshot-preparation output contracts.

Bridges read-only MT5 account facts (``app.core.models.mt5_runtime``) toward
Stage 7's ``AccountRiskSnapshot`` (``app.core.models.risk_gate_result``)
without constructing it: Stage 10B owns and persists ``rollover_equity`` for
the broker trading day and exposes only the facts it can legitimately supply
today - ``current_equity`` and ``floating_pnl``. ``realized_daily_pnl``
(Stage 10D, deal-history aggregation) and ``current_open_risk_to_stop``
(Stage 10C, open-position/symbol-stop data) are never present here, never
defaulted to zero, and never fabricated - a later Stage 10 sub-stage
constructs ``AccountRiskSnapshot`` only once both facts genuinely exist.

Neither model here is, or feeds directly into, ``AccountRiskSnapshot``: no
import of ``app.core.models.risk_gate_result`` appears in this module, and
none may be added.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode, MT5RolloverOutcome
from app.core.models.base import DomainModel, Timestamp

_USABLE_OUTCOMES: frozenset[MT5RolloverOutcome] = frozenset(
    {MT5RolloverOutcome.READY, MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY}
)
"""The only two ``MT5RolloverOutcome`` values under which a
``MT5RolloverSnapshot`` may carry a populated ``rollover_state`` - every
other outcome fails closed with ``rollover_state=None``."""


class MT5RolloverState(DomainModel):
    """Persisted, application-owned rollover fact for one broker trading day.

    ``trading_day_key`` is the broker-local calendar date (``YYYY-MM-DD``)
    at the configured rollover boundary - see
    ``app.mt5.rollover.compute_trading_day_key``. ``rollover_timezone``/
    ``rollover_hour`` are carried on the persisted state itself (not only on
    live config) so a restart can detect a changed policy underneath an
    otherwise same-day restart (``MT5RolloverOutcome.CONFIG_MISMATCH``)
    without ambiguity. ``schema_version`` lets a future persistence-format
    change be distinguished from corruption.
    """

    schema_version: Annotated[int, Field(ge=1)] = 1
    trading_day_key: Annotated[str, Field(min_length=10, max_length=10)]
    rollover_equity: Annotated[Decimal, Field(gt=0)]
    established_at: Timestamp
    rollover_timezone: Annotated[str, Field(min_length=1)]
    rollover_hour: Annotated[int, Field(ge=0, le=23)]
    establishment_mode: MT5RolloverEstablishmentMode

    @model_validator(mode="after")
    def _validate_trading_day_key_is_iso_date(self) -> Self:
        try:
            date.fromisoformat(self.trading_day_key)
        except ValueError as exc:
            raise ValueError(f"trading_day_key must be a YYYY-MM-DD calendar date: {self.trading_day_key!r}") from exc
        return self


class MT5RolloverSnapshot(DomainModel):
    """Stage 10B's complete deliverable: one rollover evaluation observation.

    ``current_equity`` and ``floating_pnl`` are mandatory, non-optional
    inputs - this snapshot is only ever built once ``MT5AccountFacts`` is
    already known to exist (``MT5ConnectivityState.AVAILABLE``); a caller
    without account facts never reaches this model at all and reports
    ``MT5RuntimeStatus``/``MT5ConnectivityState`` directly instead, so no
    "account unavailable" branch is represented here (see
    ``MT5RolloverOutcome``'s own docstring). Deliberately excludes
    ``currency`` (unused by any Stage 10B logic or by ``AccountRiskSnapshot``
    itself), ``realized_daily_pnl``, ``current_open_risk_to_stop``, and any
    embedded ``AccountRiskSnapshot`` - carrying any of those here would
    either duplicate an unrelated fact or fabricate a safety-critical one
    that is not yet legitimately available.
    """

    as_of: Timestamp
    rollover_outcome: MT5RolloverOutcome
    rollover_state: MT5RolloverState | None
    current_equity: Annotated[Decimal, Field(gt=0)]
    floating_pnl: Decimal

    @model_validator(mode="after")
    def _validate_rollover_state_presence(self) -> Self:
        usable = self.rollover_outcome in _USABLE_OUTCOMES
        if usable and self.rollover_state is None:
            raise ValueError(f"outcome {self.rollover_outcome} requires a populated rollover_state")
        if not usable and self.rollover_state is not None:
            raise ValueError(f"outcome {self.rollover_outcome} must not carry a rollover_state")
        return self


__all__ = ["MT5RolloverSnapshot", "MT5RolloverState"]
