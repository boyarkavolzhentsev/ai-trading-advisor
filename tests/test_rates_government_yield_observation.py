"""``GovernmentYieldObservation`` contract rules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.rates import GovernmentYieldType, SeriesUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.tenor import Tenor


def _observation(now: datetime, **overrides: object) -> GovernmentYieldObservation:
    fields: dict[str, object] = {
        "provider": "testrates",
        "provider_series_id": "us-10y-nominal",
        "country": "US",
        "currency": "USD",
        "yield_type": GovernmentYieldType.NOMINAL,
        "tenor": Tenor.of_years(10),
        "value": Decimal("4.10"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return GovernmentYieldObservation(**fields)


def test_constructs_with_required_fields(now: datetime) -> None:
    observation = _observation(now)
    assert observation.value == Decimal("4.10")
    assert observation.tenor.label == "10Y"
    assert observation.revision_number == 0


def test_negative_real_yield_is_valid(now: datetime) -> None:
    observation = _observation(now, yield_type=GovernmentYieldType.REAL, value=Decimal("-1.2"))
    assert observation.value == Decimal("-1.2")


def test_zero_value_is_valid(now: datetime) -> None:
    observation = _observation(now, value=Decimal("0"))
    assert observation.value == Decimal("0")


def test_none_value_is_valid_and_distinct_from_zero(now: datetime) -> None:
    observation = _observation(now, value=None)
    assert observation.value is None
    assert observation.value != Decimal("0")


def test_nominal_and_real_share_the_same_model(now: datetime) -> None:
    nominal = _observation(now, yield_type=GovernmentYieldType.NOMINAL)
    real = _observation(now, yield_type=GovernmentYieldType.REAL)
    assert type(nominal) is type(real) is GovernmentYieldObservation
    assert nominal.yield_type != real.yield_type


def test_negative_revision_number_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, revision_number=-1)


def test_naive_observation_time_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, observation_time=datetime(2026, 1, 2, 12, 0))


def test_invalid_country_shape_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, country="usa")


def test_invalid_currency_shape_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, currency="US")


def test_is_frozen(now: datetime) -> None:
    observation = _observation(now)
    with pytest.raises(ValidationError):
        observation.value = Decimal("1")  # type: ignore[misc]


def test_extra_fields_are_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, trade_direction="BUY")


@pytest.mark.parametrize(
    ("country", "currency"),
    [("US", "USD"), ("DE", "EUR"), ("GB", "GBP"), ("JP", "JPY")],
)
def test_multiple_countries_and_currencies_are_representable(now: datetime, country: str, currency: str) -> None:
    observation = _observation(now, country=country, currency=currency)
    assert observation.country == country
    assert observation.currency == currency


@pytest.mark.parametrize("tenor", [Tenor.of_months(3), Tenor.of_years(2), Tenor.of_years(5), Tenor.of_years(30)])
def test_multiple_tenors_are_representable(now: datetime, tenor: Tenor) -> None:
    observation = _observation(now, tenor=tenor)
    assert observation.tenor == tenor


def test_country_field_is_required_not_hardcoded() -> None:
    assert "country" in GovernmentYieldObservation.model_fields
    assert GovernmentYieldObservation.model_fields["country"].is_required()


def test_no_central_bank_field_exists() -> None:
    assert "central_bank" not in GovernmentYieldObservation.model_fields
