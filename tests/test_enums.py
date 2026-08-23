"""Enum membership and enum validation inside models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.enums import (
    ContractType,
    JudgeVerdictType,
    MarketRegime,
    MarketType,
    OrderSide,
    Timeframe,
    TradeDirection,
    TradeStatus,
    TradingSessionStatus,
)
from app.core.models import AgentAssessment


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (MarketType, {"US", "EU", "FX", "CRYPTO", "METALS", "ENERGIES"}),
        (TradeDirection, {"LONG", "SHORT", "NEUTRAL", "WAIT"}),
        (ContractType, {"SPOT", "PERPETUAL"}),
        (OrderSide, {"BUY", "SELL"}),
        (
            TradeStatus,
            {
                "PENDING",
                "FILLED",
                "OPEN",
                "CLOSED",
                "WIN",
                "LOSS",
                "BREAKEVEN",
                "NOT_FILLED",
                "EXPIRED",
                "CANCELLED",
            },
        ),
        (JudgeVerdictType, {"APPROVE", "REJECT", "WAIT"}),
        (
            MarketRegime,
            {
                "TRENDING",
                "RANGING",
                "HIGH_VOLATILITY",
                "LOW_VOLATILITY",
                "LOW_LIQUIDITY",
                "RISK_ON",
                "RISK_OFF",
                "UNKNOWN",
            },
        ),
        (Timeframe, {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"}),
        (
            TradingSessionStatus,
            {
                "ACTIVE",
                "REDUCED_RISK",
                "CAPITAL_PRESERVATION",
                "TARGET_REACHED",
                "LOSS_LIMIT_REACHED",
                "LOCKED",
            },
        ),
    ],
)
def test_enum_members(enum_cls: type, expected: set[str]) -> None:
    assert {member.value for member in enum_cls} == expected


def test_model_accepts_enum_value_as_string(now: datetime) -> None:
    assessment = AgentAssessment(
        agent_name="technical",
        direction="LONG",
        confidence=0.5,
        timestamp=now,
    )
    assert assessment.direction is TradeDirection.LONG


def test_model_rejects_unknown_enum_value(now: datetime) -> None:
    with pytest.raises(ValidationError):
        AgentAssessment(
            agent_name="technical",
            direction="SIDEWAYS",
            confidence=0.5,
            timestamp=now,
        )
