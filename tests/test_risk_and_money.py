"""Risk percentage and money-management envelope validation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.models import MoneyManagementDecision, RiskAssessment


@pytest.mark.parametrize("risk_percent", ["0", "0.5", "1.5", "100"])
def test_valid_risk_percent_is_accepted(risk_percent: str) -> None:
    assessment = RiskAssessment(
        approved=True,
        risk_percent=Decimal(risk_percent),
        max_loss=Decimal("1500"),
    )
    assert assessment.risk_percent == Decimal(risk_percent)


@pytest.mark.parametrize("risk_percent", ["-0.1", "-1", "100.1", "1000"])
def test_invalid_risk_percent_is_rejected(risk_percent: str) -> None:
    with pytest.raises(ValidationError):
        RiskAssessment(
            approved=False,
            risk_percent=Decimal(risk_percent),
            max_loss=Decimal("0"),
        )


def test_negative_max_loss_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskAssessment(
            approved=True,
            risk_percent=Decimal("1"),
            max_loss=Decimal("-100"),
        )


def test_money_management_defaults_leave_sizing_unresolved() -> None:
    decision = MoneyManagementDecision(
        equity=Decimal("98500"),
        daily_risk_budget=Decimal("1477.50"),
        available_new_risk=Decimal("1477.50"),
        recommended_risk_percent=Decimal("1.0"),
    )
    assert decision.used_open_risk == Decimal("0")
    assert decision.recommended_lot is None
    assert decision.margin_required is None
    assert decision.leverage is None


def test_available_new_risk_may_be_negative_when_carried_risk_exceeds_budget() -> None:
    decision = MoneyManagementDecision(
        equity=Decimal("98500"),
        daily_risk_budget=Decimal("1477.50"),
        used_open_risk=Decimal("1600"),
        available_new_risk=Decimal("-122.50"),
        recommended_risk_percent=Decimal("0"),
    )
    assert decision.available_new_risk < 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recommended_lot", Decimal("-0.1")),
        ("leverage", Decimal("0")),
        ("margin_required", Decimal("-1")),
        ("recommended_risk_percent", Decimal("101")),
    ],
)
def test_invalid_money_management_values_are_rejected(
    field: str, value: Decimal
) -> None:
    payload = {
        "equity": Decimal("100000"),
        "daily_risk_budget": Decimal("1500"),
        "available_new_risk": Decimal("1500"),
        "recommended_risk_percent": Decimal("1.0"),
        field: value,
    }
    with pytest.raises(ValidationError):
        MoneyManagementDecision(**payload)
