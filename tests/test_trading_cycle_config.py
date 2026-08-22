"""TradingCycleConfig contract."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import TradingCycleConfig


def test_defaults_match_documented_example() -> None:
    config = TradingCycleConfig()
    assert config.starting_equity == Decimal("100000")
    assert config.target_profit_percent == Decimal("6.0")
    assert config.daily_risk_limit_percent == Decimal("1.5")
    assert config.max_cycle_drawdown_percent == Decimal("7.5")
    assert config.cycle_days == 14


def test_values_are_configurable() -> None:
    config = TradingCycleConfig(
        starting_equity=Decimal("25000"),
        target_profit_percent=Decimal("4"),
        daily_risk_limit_percent=Decimal("1"),
        max_cycle_drawdown_percent=Decimal("5"),
        cycle_days=7,
    )
    assert config.cycle_days == 7
    assert config.daily_risk_limit_percent == Decimal("1")


def test_daily_risk_percent_supports_exact_decimal_budget() -> None:
    """Rollover budget arithmetic must be exact (98,500 * 1.5% = 1,477.50)."""
    config = TradingCycleConfig()
    rollover_equity = Decimal("98500")
    budget = rollover_equity * config.daily_risk_limit_percent / Decimal("100")
    assert budget == Decimal("1477.50")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("starting_equity", Decimal("0")),
        ("starting_equity", Decimal("-1")),
        ("target_profit_percent", Decimal("0")),
        ("target_profit_percent", Decimal("101")),
        ("daily_risk_limit_percent", Decimal("0")),
        ("daily_risk_limit_percent", Decimal("-1.5")),
        ("max_cycle_drawdown_percent", Decimal("0")),
        ("cycle_days", 0),
        ("cycle_days", -14),
    ],
)
def test_invalid_config_values_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TradingCycleConfig(**{field: value})


def test_daily_limit_above_cycle_drawdown_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        TradingCycleConfig(
            daily_risk_limit_percent=Decimal("8"),
            max_cycle_drawdown_percent=Decimal("7.5"),
        )
