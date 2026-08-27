"""``RateDecisionDetail`` contract and its attachment rules on ``EconomicEvent``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.economic_calendar import CentralBank, EconomicCategory, EconomicEventStatus
from app.core.models.economic_event import EconomicEvent, RateDecisionDetail


def _rate_event(now: datetime, **overrides: object) -> EconomicEvent:
    fields: dict[str, object] = {
        "provider": "testcal",
        "provider_event_id": "fomc-2026-01",
        "country": "US",
        "currency": "USD",
        "category": EconomicCategory.RATE_DECISION,
        "name": "FOMC Rate Decision",
        "event_time": now,
        "received_at": now,
        "status": EconomicEventStatus.SCHEDULED,
        "rate_decision_detail": RateDecisionDetail(
            central_bank=CentralBank.FED,
            policy_rate_previous=Decimal("5.25"),
            policy_rate_expected=Decimal("5.00"),
        ),
    }
    fields.update(overrides)
    return EconomicEvent(**fields)


def test_rate_decision_detail_constructs_with_facts_only(now: datetime) -> None:
    detail = RateDecisionDetail(
        central_bank=CentralBank.ECB,
        policy_rate_previous=Decimal("4.5"),
        policy_rate_expected=Decimal("4.25"),
        policy_rate_actual=Decimal("4.25"),
        statement_time=now,
    )
    assert detail.central_bank is CentralBank.ECB
    assert detail.policy_rate_actual == Decimal("4.25")


def test_rate_decision_detail_allows_negative_policy_rate(now: datetime) -> None:
    detail = RateDecisionDetail(central_bank=CentralBank.BOJ, policy_rate_actual=Decimal("-0.10"))
    assert detail.policy_rate_actual == Decimal("-0.10")


def test_rate_decision_detail_has_no_interpretation_fields() -> None:
    forbidden = {"hawkish", "dovish", "bullish", "bearish", "trading_impact", "rate_change_bps"}
    assert forbidden.isdisjoint(RateDecisionDetail.model_fields)


def test_rate_decision_category_requires_detail(now: datetime) -> None:
    with pytest.raises(ValidationError):
        EconomicEvent(
            provider="testcal",
            provider_event_id="fomc-2026-01",
            country="US",
            currency="USD",
            category=EconomicCategory.RATE_DECISION,
            name="FOMC Rate Decision",
            event_time=now,
            received_at=now,
            status=EconomicEventStatus.SCHEDULED,
        )


def test_non_rate_decision_category_forbids_detail(now: datetime) -> None:
    with pytest.raises(ValidationError):
        EconomicEvent(
            provider="testcal",
            provider_event_id="cpi-2026-01",
            country="US",
            currency="USD",
            category=EconomicCategory.CPI,
            name="CPI YoY",
            event_time=now,
            received_at=now,
            status=EconomicEventStatus.SCHEDULED,
            rate_decision_detail=RateDecisionDetail(central_bank=CentralBank.FED),
        )


def test_rate_decision_scheduled_is_valid(now: datetime) -> None:
    event = _rate_event(now)
    assert event.status is EconomicEventStatus.SCHEDULED
    assert event.actual is None
    assert event.rate_decision_detail.policy_rate_actual is None


def test_rate_decision_released_requires_matching_actual_presence(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _rate_event(
            now,
            status=EconomicEventStatus.RELEASED,
            actual=Decimal("5.00"),
            rate_decision_detail=RateDecisionDetail(central_bank=CentralBank.FED),  # policy_rate_actual missing
        )


def test_rate_decision_released_with_consistent_actual_is_valid(now: datetime) -> None:
    event = _rate_event(
        now,
        status=EconomicEventStatus.RELEASED,
        actual=Decimal("5.00"),
        rate_decision_detail=RateDecisionDetail(
            central_bank=CentralBank.FED,
            policy_rate_previous=Decimal("5.25"),
            policy_rate_expected=Decimal("5.00"),
            policy_rate_actual=Decimal("5.00"),
        ),
    )
    assert event.rate_decision_detail.policy_rate_actual == Decimal("5.00")


def test_rate_decision_detail_actual_without_event_actual_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _rate_event(
            now,
            status=EconomicEventStatus.SCHEDULED,
            rate_decision_detail=RateDecisionDetail(
                central_bank=CentralBank.FED,
                policy_rate_actual=Decimal("5.00"),
            ),
        )
