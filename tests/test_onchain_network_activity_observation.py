"""Stage 4E ``NetworkActivityObservation`` model validation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.onchain import OnChainUnit
from app.core.models.network_activity_observation import NetworkActivityObservation


def _observation(now: datetime, **overrides: object) -> NetworkActivityObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-active-addresses",
        "asset": "BTC",
        "network": "bitcoin",
        "observation_time": now,
        "received_at": now,
        "active_addresses": 950_000,
    }
    fields.update(overrides)
    return NetworkActivityObservation(**fields)


def test_required_fields_construct_a_valid_observation(now: datetime) -> None:
    observation = _observation(now)
    assert observation.provider == "glassnode"
    assert observation.asset == "BTC"
    assert observation.network == "bitcoin"


def test_active_addresses_is_int(now: datetime) -> None:
    observation = _observation(now, active_addresses=123)
    assert isinstance(observation.active_addresses, int)


def test_active_addresses_zero_is_valid_not_missing(now: datetime) -> None:
    observation = _observation(now, active_addresses=0)
    assert observation.active_addresses == 0
    assert observation.active_addresses is not None


def test_negative_active_addresses_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=-1)


def test_negative_transaction_count_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None, transaction_count=-1)


def test_transaction_volume_requires_paired_unit(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None, transaction_volume=Decimal("100"))


def test_transaction_volume_unit_without_value_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None, transaction_volume_unit=OnChainUnit.USD)


def test_transaction_volume_with_paired_unit_is_valid(now: datetime) -> None:
    observation = _observation(
        now,
        active_addresses=None,
        transaction_volume=Decimal("12345.67"),
        transaction_volume_unit=OnChainUnit.USD,
    )
    assert observation.transaction_volume == Decimal("12345.67")
    assert observation.transaction_volume_unit is OnChainUnit.USD


def test_fees_total_requires_paired_unit(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None, fees_total=Decimal("1.5"))


def test_fees_total_with_paired_unit_is_valid(now: datetime) -> None:
    observation = _observation(
        now, active_addresses=None, fees_total=Decimal("1.5"), fees_unit=OnChainUnit.NATIVE_ASSET
    )
    assert observation.fees_total == Decimal("1.5")
    assert observation.fees_unit is OnChainUnit.NATIVE_ASSET


def test_negative_transaction_volume_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(
            now,
            active_addresses=None,
            transaction_volume=Decimal("-1"),
            transaction_volume_unit=OnChainUnit.USD,
        )


def test_negative_fees_total_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None, fees_total=Decimal("-1"), fees_unit=OnChainUnit.USD)


def test_at_least_one_activity_metric_required(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, active_addresses=None)


def test_period_window_both_present_is_valid(now: datetime) -> None:
    observation = _observation(now, period_start=now - timedelta(days=1), period_end=now)
    assert observation.period_start is not None
    assert observation.period_end is not None


def test_period_window_both_absent_is_valid(now: datetime) -> None:
    observation = _observation(now)
    assert observation.period_start is None
    assert observation.period_end is None


def test_period_start_without_period_end_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, period_start=now - timedelta(days=1))


def test_period_end_without_period_start_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, period_end=now)


def test_asset_and_network_are_independent_dimensions(now: datetime) -> None:
    btc = _observation(now, asset="BTC", network="bitcoin")
    eth = _observation(now, asset="ETH", network="ethereum")
    assert btc.asset != eth.asset
    assert btc.network != eth.network


def test_publication_time_before_observation_time_is_accepted(now: datetime) -> None:
    """No cross-field chronological invariant is enforced - provider
    timestamps are preserved exactly as reported."""
    earlier = now - timedelta(days=1)
    observation = _observation(now, publication_time=earlier)
    assert observation.publication_time == earlier


def test_model_is_frozen(now: datetime) -> None:
    observation = _observation(now)
    with pytest.raises(ValidationError):
        observation.active_addresses = 1  # type: ignore[misc]


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unexpected_field="value")


def test_naive_datetime_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, observation_time=datetime(2026, 1, 1))
