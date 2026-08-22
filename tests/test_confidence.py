"""Confidence bounds across every model that carries a confidence score."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.models import AgentAssessment, JudgeVerdict, TradeDecision, TradeSetup


def _payloads(now: datetime) -> dict[type, dict[str, Any]]:
    return {
        AgentAssessment: {
            "agent_name": "technical",
            "direction": "LONG",
            "timestamp": now,
        },
        TradeDecision: {"direction": "LONG", "timestamp": now},
        JudgeVerdict: {"verdict": "APPROVE", "timestamp": now},
        TradeSetup: {
            "symbol": "TEST",
            "market": "FX",
            "direction": "LONG",
            "signal_time": now,
            "valid_until": now + timedelta(minutes=5),
            "entry_price": Decimal("100"),
            "stop_loss": Decimal("99"),
        },
    }


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_inside_bounds_is_accepted(
    now: datetime, confidence: float
) -> None:
    for model_cls, payload in _payloads(now).items():
        assert model_cls(confidence=confidence, **payload).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.1, -1.0, 1.01, 2.0])
def test_confidence_outside_bounds_is_rejected(
    now: datetime, confidence: float
) -> None:
    for model_cls, payload in _payloads(now).items():
        with pytest.raises(ValidationError):
            model_cls(confidence=confidence, **payload)
