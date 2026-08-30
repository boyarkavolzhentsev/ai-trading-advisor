"""Stage 8 ``TradingCycleConfig`` extension: ``portfolio_risk_limit_percent``
default and its invariant against ``max_cycle_drawdown_percent``, and
confirmation that existing Stage 7 defaults are unchanged."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config.trading_cycle import TradingCycleConfig


def test_default_portfolio_risk_limit_percent() -> None:
    config = TradingCycleConfig()
    assert config.portfolio_risk_limit_percent == Decimal("6")


def test_portfolio_exceeding_drawdown_rejected() -> None:
    with pytest.raises(ValidationError):
        TradingCycleConfig(portfolio_risk_limit_percent=Decimal("8.0"))


def test_portfolio_equal_to_drawdown_accepted() -> None:
    config = TradingCycleConfig(portfolio_risk_limit_percent=Decimal("7.5"))
    assert config.portfolio_risk_limit_percent == Decimal("7.5")


def test_existing_stage7_defaults_unchanged() -> None:
    config = TradingCycleConfig()
    assert config.daily_risk_limit_percent == Decimal("1.5")
    assert config.per_trade_risk_limit_percent == Decimal("0.5")
    assert config.max_cycle_drawdown_percent == Decimal("7.5")
