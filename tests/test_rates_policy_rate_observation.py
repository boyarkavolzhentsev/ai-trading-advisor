"""``PolicyRateObservation`` contract rules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import PolicyRateKind, SeriesUnit
from app.core.models.policy_rate_observation import PolicyRateObservation


def _observation(now: datetime, **overrides: object) -> PolicyRateObservation:
    fields: dict[str, object] = {
        "provider": "testrates",
        "provider_series_id": "fed-target-lower",
        "central_bank": CentralBank.FED,
        "currency": "USD",
        "rate_kind": PolicyRateKind.TARGET_LOWER,
        "value": Decimal("4.25"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return PolicyRateObservation(**fields)


def test_constructs_with_required_fields(now: datetime) -> None:
    observation = _observation(now)
    assert observation.value == Decimal("4.25")
    assert observation.revision_number == 0
    assert observation.publication_time is None
    assert observation.source_url is None


def test_negative_value_is_valid(now: datetime) -> None:
    observation = _observation(now, value=Decimal("-0.5"))
    assert observation.value == Decimal("-0.5")


def test_zero_value_is_valid(now: datetime) -> None:
    observation = _observation(now, value=Decimal("0"))
    assert observation.value == Decimal("0")


def test_none_value_is_valid_and_distinct_from_zero(now: datetime) -> None:
    observation = _observation(now, value=None)
    assert observation.value is None
    assert observation.value != Decimal("0")


def test_negative_revision_number_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, revision_number=-1)


def test_positive_revision_number_is_accepted(now: datetime) -> None:
    observation = _observation(now, revision_number=1)
    assert observation.revision_number == 1


def test_naive_observation_time_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, observation_time=datetime(2026, 1, 2, 12, 0))


def test_naive_received_at_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, received_at=datetime(2026, 1, 2, 12, 0))


def test_empty_provider_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, provider="")


def test_empty_provider_series_id_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, provider_series_id="")


def test_invalid_currency_shape_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, currency="US")


def test_missing_unit_is_rejected(now: datetime) -> None:
    fields = {
        "provider": "testrates",
        "provider_series_id": "fed-target-lower",
        "central_bank": CentralBank.FED,
        "currency": "USD",
        "rate_kind": PolicyRateKind.TARGET_LOWER,
        "value": Decimal("4.25"),
        "observation_time": now,
        "received_at": now,
    }
    with pytest.raises(ValidationError):
        PolicyRateObservation(**fields)


def test_is_frozen(now: datetime) -> None:
    observation = _observation(now)
    with pytest.raises(ValidationError):
        observation.value = Decimal("1")  # type: ignore[misc]


def test_extra_fields_are_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, trade_direction="BUY")


@pytest.mark.parametrize(
    "rate_kind",
    [PolicyRateKind.TARGET, PolicyRateKind.TARGET_LOWER, PolicyRateKind.TARGET_UPPER, PolicyRateKind.EFFECTIVE],
)
def test_all_policy_rate_kinds_are_representable(now: datetime, rate_kind: PolicyRateKind) -> None:
    observation = _observation(now, rate_kind=rate_kind)
    assert observation.rate_kind is rate_kind


def test_target_range_is_two_separate_observations_not_averaged(now: datetime) -> None:
    lower = _observation(now, rate_kind=PolicyRateKind.TARGET_LOWER, value=Decimal("4.25"))
    upper = _observation(now, rate_kind=PolicyRateKind.TARGET_UPPER, value=Decimal("4.50"))
    assert lower.value != upper.value
    assert lower.rate_kind != upper.rate_kind
    assert lower != upper


@pytest.mark.parametrize("central_bank", list(CentralBank))
def test_multiple_central_banks_are_representable(now: datetime, central_bank: CentralBank) -> None:
    observation = _observation(now, central_bank=central_bank)
    assert observation.central_bank is central_bank


def test_no_country_field_exists() -> None:
    assert "country" not in PolicyRateObservation.model_fields


def test_no_coupling_to_rate_decision_detail_shape() -> None:
    assert "rate_decision_detail" not in PolicyRateObservation.model_fields
    assert "provider_event_id" not in PolicyRateObservation.model_fields
    assert "category" not in PolicyRateObservation.model_fields
    assert "status" not in PolicyRateObservation.model_fields
