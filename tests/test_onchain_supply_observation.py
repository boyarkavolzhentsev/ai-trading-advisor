"""Stage 4E ``SupplyObservation`` model validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.models.supply_observation import SupplyObservation


def _observation(now: datetime, **overrides: object) -> SupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-supply",
        "asset": "BTC",
        "network": "bitcoin",
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("19800000"),
    }
    fields.update(overrides)
    return SupplyObservation(**fields)


def test_required_fields_construct_a_valid_observation(now: datetime) -> None:
    observation = _observation(now)
    assert observation.total_supply == Decimal("19800000")


def test_total_supply_is_decimal(now: datetime) -> None:
    observation = _observation(now, total_supply=Decimal("21000000"))
    assert isinstance(observation.total_supply, Decimal)


def test_zero_supply_is_valid_not_missing(now: datetime) -> None:
    observation = _observation(now, total_supply=Decimal("0"))
    assert observation.total_supply == Decimal("0")
    assert observation.total_supply is not None


def test_negative_total_supply_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=Decimal("-1"))


def test_negative_circulating_supply_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=None, circulating_supply=Decimal("-1"))


def test_circulating_supply_alone_is_sufficient(now: datetime) -> None:
    observation = _observation(now, total_supply=None, circulating_supply=Decimal("19700000"))
    assert observation.total_supply is None
    assert observation.circulating_supply == Decimal("19700000")


def test_at_least_one_supply_value_required(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=None, circulating_supply=None)


def test_no_unit_field_exists() -> None:
    """total_supply/circulating_supply are always native-asset units by
    definition - no unit field exists on this model."""
    assert "unit" not in SupplyObservation.model_fields
    assert "total_supply_unit" not in SupplyObservation.model_fields


def test_period_window_both_or_neither(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, period_start=now - timedelta(days=1))
    observation = _observation(now, period_start=now - timedelta(days=1), period_end=now)
    assert observation.period_start is not None


def test_exact_decimal_precision_preserved(now: datetime) -> None:
    exact = Decimal("19812345.123456789")
    observation = _observation(now, total_supply=exact)
    assert observation.total_supply == exact
    assert str(observation.total_supply) == str(exact)


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unexpected_field="value")
