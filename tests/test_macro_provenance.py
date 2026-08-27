"""``MacroProvenance`` contract rules."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.macro.provenance import EconomicDataSource, MacroProvenance


def test_provenance_constructs_with_required_fields(now: datetime) -> None:
    provenance = MacroProvenance(
        provider="testcal",
        source=EconomicDataSource.ECONOMIC_CALENDAR,
        fetched_at=now,
    )
    assert provenance.provider == "testcal"
    assert provenance.provider_timestamp is None
    assert provenance.source_url is None


def test_label_property_mirrors_market_data_provenance_shape(now: datetime) -> None:
    provenance = MacroProvenance(provider="testcal", source=EconomicDataSource.RATE_DECISION, fetched_at=now)
    assert provenance.label == "testcal:RATE_DECISION"


def test_naive_fetched_at_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MacroProvenance(
            provider="testcal",
            source=EconomicDataSource.ECONOMIC_CALENDAR,
            fetched_at=datetime(2026, 1, 2, 12, 0),
        )


def test_empty_provider_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        MacroProvenance(provider="", source=EconomicDataSource.ECONOMIC_CALENDAR, fetched_at=now)


def test_provenance_is_frozen(now: datetime) -> None:
    provenance = MacroProvenance(provider="testcal", source=EconomicDataSource.ECONOMIC_CALENDAR, fetched_at=now)
    with pytest.raises(ValidationError):
        provenance.provider = "other"  # type: ignore[misc]


def test_no_reliability_class_field_in_stage_4a() -> None:
    assert "reliability_class" not in MacroProvenance.model_fields


def test_no_secret_shaped_fields() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for field_name in MacroProvenance.model_fields:
        lowered = field_name.lower()
        assert not any(term in lowered for term in forbidden_substrings), field_name
