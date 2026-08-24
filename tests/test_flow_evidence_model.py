"""Tests for app.core.models.flow_evidence.FlowEvidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.enums.quality import FeatureQuality
from app.core.models.flow_evidence import FlowEvidence

TS = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence(**overrides: object) -> FlowEvidence:
    fields = dict(
        feature_name="taker_flow.delta",
        window="1m",
        observed_value="1.5",
        reference_value=None,
        quality=FeatureQuality.VALID,
        source_timestamp=TS,
        provenance="binance:agg_trade",
    )
    fields.update(overrides)
    return FlowEvidence(**fields)


def test_valid_evidence_roundtrips() -> None:
    evidence = _evidence()
    dumped = evidence.model_dump()
    restored = FlowEvidence.model_validate(dumped)
    assert restored == evidence


def test_feature_name_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        _evidence(feature_name="")


def test_provenance_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        _evidence(provenance="")


def test_observed_value_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        _evidence(observed_value="")


def test_window_and_reference_value_optional() -> None:
    evidence = _evidence(window=None, reference_value=None)
    assert evidence.window is None
    assert evidence.reference_value is None


def test_frozen_immutable() -> None:
    evidence = _evidence()
    with pytest.raises(ValidationError):
        evidence.feature_name = "other"  # type: ignore[misc]
