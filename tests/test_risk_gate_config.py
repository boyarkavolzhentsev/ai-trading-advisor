"""Stage 7 ``TradingCycleConfig`` extension: ``per_trade_risk_limit_percent``
default and its invariant against ``daily_risk_limit_percent``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config.trading_cycle import TradingCycleConfig


def test_default_daily_and_per_trade_percentages() -> None:
    config = TradingCycleConfig()
    assert config.daily_risk_limit_percent == Decimal("1.5")
    assert config.per_trade_risk_limit_percent == Decimal("0.5")


def test_per_trade_exceeding_daily_rejected() -> None:
    with pytest.raises(ValidationError):
        TradingCycleConfig(per_trade_risk_limit_percent=Decimal("2.0"))


def test_per_trade_equal_to_daily_accepted() -> None:
    config = TradingCycleConfig(per_trade_risk_limit_percent=Decimal("1.5"))
    assert config.per_trade_risk_limit_percent == Decimal("1.5")


def test_max_cycle_drawdown_behavior_unchanged() -> None:
    config = TradingCycleConfig()
    assert config.max_cycle_drawdown_percent == Decimal("7.5")
    with pytest.raises(ValidationError):
        TradingCycleConfig(daily_risk_limit_percent=Decimal("10.0"))
