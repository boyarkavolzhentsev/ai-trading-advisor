"""``RatesProvenance`` contract rules."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.rates.provenance import RatesDataSource, RatesProvenance


def test_provenance_constructs_with_required_fields(now: datetime) -> None:
    provenance = RatesProvenance(provider="testrates", source=RatesDataSource.POLICY_RATE, fetched_at=now)
    assert provenance.provider == "testrates"
    assert provenance.provider_timestamp is None
    assert provenance.source_url is None


def test_label_property_mirrors_macro_provenance_shape(now: datetime) -> None:
    provenance = RatesProvenance(provider="testrates", source=RatesDataSource.GOVERNMENT_YIELD, fetched_at=now)
    assert provenance.label == "testrates:GOVERNMENT_YIELD"


def test_naive_fetched_at_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RatesProvenance(
            provider="testrates",
            source=RatesDataSource.POLICY_RATE,
            fetched_at=datetime(2026, 1, 2, 12, 0),
        )


def test_empty_provider_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        RatesProvenance(provider="", source=RatesDataSource.POLICY_RATE, fetched_at=now)


def test_provenance_is_frozen(now: datetime) -> None:
    provenance = RatesProvenance(provider="testrates", source=RatesDataSource.POLICY_RATE, fetched_at=now)
    with pytest.raises(ValidationError):
        provenance.provider = "other"  # type: ignore[misc]


def test_no_reliability_class_field_in_stage_4b() -> None:
    assert "reliability_class" not in RatesProvenance.model_fields


def test_no_secret_shaped_fields() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for field_name in RatesProvenance.model_fields:
        lowered = field_name.lower()
        assert not any(term in lowered for term in forbidden_substrings), field_name


def test_both_source_kinds_exist() -> None:
    assert {member.value for member in RatesDataSource} == {"POLICY_RATE", "GOVERNMENT_YIELD"}
