"""Shared fixtures for Stage 10B rollover tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode
from app.core.models.mt5_rollover import MT5RolloverState

__all__ = [
    "NOW",
    "UTC_POLICY",
    "default_rollover_state",
]

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

UTC_POLICY = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0)


def default_rollover_state(**overrides: object) -> MT5RolloverState:
    fields: dict[str, object] = {
        "trading_day_key": "2026-01-01",
        "rollover_equity": Decimal("100000"),
        "established_at": NOW,
        "rollover_timezone": "UTC",
        "rollover_hour": 0,
        "establishment_mode": MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP,
    }
    fields.update(overrides)
    return MT5RolloverState(**fields)
