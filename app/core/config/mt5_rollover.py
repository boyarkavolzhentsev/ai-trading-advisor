"""Stage 10B rollover policy configuration contract.

Stage-10-owned, not Stage 7's risk envelope: nothing in ``TradingCycleConfig``
depends on this, and nothing here is read by Stage 7/8/9. Kept as a sibling
of ``TradingCycleConfig`` in ``app/core/config`` (not under ``app/mt5``)
because every other pydantic config/domain contract in this repository lives
under ``app/core`` - ``app/mt5`` holds only the impure adapter, pure
transition logic, protocols and errors, never model/config definitions
(enforced by ``tests/test_mt5_module_hygiene.py``'s ``models.py``/``enums.py``
denylist for that package).

Secretless by construction: no credential, path, or connection fact belongs
here - only the deterministic broker/server trading-day boundary policy.
"""

from __future__ import annotations

from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.core.models.base import DomainModel


class MT5RolloverPolicyConfig(DomainModel):
    """Deterministic broker/server trading-day rollover boundary policy.

    ``rollover_timezone`` has no default: the MetaTrader5 Python API exposes
    no reliable broker/server timezone fact (confirmed absent from both
    ``account_info()`` and ``terminal_info()``), so the operator must state
    the specific broker's documented server timezone explicitly as an IANA
    zone name - a wrong default would silently mis-key every trading day.
    ``rollover_hour`` defaults to ``0`` (server-clock midnight, the
    conventional broker trading-day boundary). No ``rollover_minute``: no
    audited requirement needs finer-than-hour granularity in V1, and adding
    one later is a non-breaking additive field.
    """

    rollover_timezone: Annotated[str, Field(min_length=1)]
    rollover_hour: Annotated[int, Field(ge=0, le=23)] = 0

    @model_validator(mode="after")
    def _validate_rollover_timezone(self) -> Self:
        try:
            ZoneInfo(self.rollover_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown rollover_timezone: {self.rollover_timezone!r}") from exc
        return self


__all__ = ["MT5RolloverPolicyConfig"]
