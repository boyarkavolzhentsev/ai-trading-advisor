"""MQL5 Calendar Bridge producer timezone policy configuration.

``server_timezone`` has no default: MQL5 exposes no API that returns the
broker's own server-timezone/DST rule table for an arbitrary past or future
date (``TimeGMT()``/``TimeGMTOffset()``/``TimeDaylightSavings()`` all resolve
relative to the client terminal's *current* local OS timezone state, never
the broker server's own rules) - mirrors the identical, already-approved
rationale for ``app.core.config.mt5_rollover.MT5RolloverPolicyConfig.
rollover_timezone`` ("the MetaTrader5 Python API exposes no reliable
broker/server timezone fact... a wrong default would silently mis-key").
The operator must state the specific broker's documented server timezone
explicitly as an IANA zone name; a wrong default here would silently
mislabel every high-impact event's timing.

Secretless by construction: no credential, path, or connection fact belongs
here - only the deterministic server-local -> UTC conversion policy.
"""

from __future__ import annotations

from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.core.models.base import DomainModel


class HighImpactEventCalendarTimezoneConfig(DomainModel):
    """Operator-declared IANA timezone the MQL5 calendar bridge's trade
    server clock is known to follow.

    Never inferred from a live-observed ``observed_offset_seconds`` sample
    (a single sample proves only what the offset was at one instant, never
    the broker's general DST rule) - this is a deterministic, auditable
    operator attestation, exactly parallel to ``MT5RolloverPolicyConfig.
    rollover_timezone``.
    """

    server_timezone: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def _validate_server_timezone(self) -> Self:
        try:
            ZoneInfo(self.server_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown server_timezone: {self.server_timezone!r}") from exc
        return self


__all__ = ["HighImpactEventCalendarTimezoneConfig"]
