"""Stage 4A ``EconomicEvent`` contract rules: lifecycle, zero-vs-None, categories."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
from app.core.models.economic_event import EconomicEvent


def _event(now: datetime, **overrides: object) -> EconomicEvent:
    fields: dict[str, object] = {
        "provider": "testcal",
        "provider_event_id": "cpi-2026-01",
        "country": "US",
        "currency": "USD",
        "category": EconomicCategory.CPI,
        "name": "CPI YoY",
        "event_time": now,
        "received_at": now,
        "status": EconomicEventStatus.SCHEDULED,
    }
    fields.update(overrides)
    return EconomicEvent(**fields)


def test_scheduled_event_with_no_actual_is_valid(now: datetime) -> None:
    event = _event(now)
    assert event.status is EconomicEventStatus.SCHEDULED
    assert event.actual is None
    assert event.revision_number == 0


def test_zero_actual_is_distinct_from_none(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0"), publication_time=now)
    assert event.actual == Decimal("0")
    assert event.actual is not None


def test_released_event_requires_actual(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.RELEASED)


def test_scheduled_event_must_not_carry_actual(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.SCHEDULED, actual=Decimal("1"))


def test_postponed_event_must_not_carry_actual(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.POSTPONED, actual=Decimal("1"))


def test_cancelled_event_must_not_carry_actual(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.CANCELLED, actual=Decimal("1"))


def test_postponed_event_is_valid_with_no_actual(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.POSTPONED)
    assert event.status is EconomicEventStatus.POSTPONED


def test_cancelled_event_is_valid_with_no_actual(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.CANCELLED)
    assert event.status is EconomicEventStatus.CANCELLED


def test_revised_event_requires_positive_revision_number(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.REVISED, actual=Decimal("1"), revision_number=0)


def test_revised_event_with_positive_revision_number_is_valid(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.REVISED, actual=Decimal("1.1"), revision_number=1)
    assert event.status is EconomicEventStatus.REVISED
    assert event.revision_number == 1


def test_released_event_must_have_revision_number_zero(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("1"), revision_number=1)


def test_revision_number_must_not_be_negative(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, status=EconomicEventStatus.REVISED, actual=Decimal("1"), revision_number=-1)


def test_naive_event_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(datetime(2026, 1, 2, 12, 0))  # no tzinfo


def test_naive_received_at_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        EconomicEvent(
            provider="testcal",
            provider_event_id="cpi-2026-01",
            country="US",
            currency="USD",
            category=EconomicCategory.CPI,
            name="CPI YoY",
            event_time=now,
            received_at=datetime(2026, 1, 2, 12, 0),
            status=EconomicEventStatus.SCHEDULED,
        )


def test_category_other_requires_category_raw(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, category=EconomicCategory.OTHER)


def test_category_other_with_category_raw_is_valid(now: datetime) -> None:
    event = _event(now, category=EconomicCategory.OTHER, category_raw="Wholesale Inventories MoM")
    assert event.category is EconomicCategory.OTHER
    assert event.category_raw == "Wholesale Inventories MoM"


def test_category_raw_optional_for_known_category(now: datetime) -> None:
    event = _event(now)
    assert event.category_raw is None


@pytest.mark.parametrize(
    "category",
    [
        EconomicCategory.CPI,
        EconomicCategory.CORE_CPI,
        EconomicCategory.PPI,
        EconomicCategory.PCE,
        EconomicCategory.CORE_PCE,
        EconomicCategory.NON_FARM_PAYROLLS,
        EconomicCategory.UNEMPLOYMENT_RATE,
        EconomicCategory.JOBLESS_CLAIMS,
        EconomicCategory.GDP,
        EconomicCategory.RETAIL_SALES,
        EconomicCategory.PMI_ISM,
        EconomicCategory.CONSUMER_CONFIDENCE,
    ],
)
def test_every_scope_category_constructs(now: datetime, category: EconomicCategory) -> None:
    event = _event(now, category=category)
    assert event.category is category


@pytest.mark.parametrize("country,currency", [("US", "USD"), ("DE", "EUR"), ("GB", "GBP"), ("JP", "JPY")])
def test_multiple_countries_and_currencies(now: datetime, country: str, currency: str) -> None:
    event = _event(now, country=country, currency=currency)
    assert event.country == country
    assert event.currency == currency


@pytest.mark.parametrize("country", ["us", "USA", "U", ""])
def test_invalid_country_code_rejected(now: datetime, country: str) -> None:
    with pytest.raises(ValidationError):
        _event(now, country=country)


@pytest.mark.parametrize("currency", ["usd", "US", "USDD", ""])
def test_invalid_currency_code_rejected(now: datetime, currency: str) -> None:
    with pytest.raises(ValidationError):
        _event(now, currency=currency)


def test_empty_provider_event_id_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, provider_event_id="")


def test_empty_provider_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, provider="")


def test_event_is_frozen(now: datetime) -> None:
    event = _event(now)
    with pytest.raises(ValidationError):
        event.provider = "other"  # type: ignore[misc]


def test_unknown_field_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _event(now, direction="LONG")


def test_no_computed_surprise_field_exists() -> None:
    assert "surprise" not in EconomicEvent.model_fields
    assert "surprise_percent" not in EconomicEvent.model_fields
