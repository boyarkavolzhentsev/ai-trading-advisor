"""Stage 4E ``ExchangeFlowObservation`` model validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.onchain import OnChainUnit
from app.core.models.exchange_flow_observation import ExchangeFlowObservation


def _observation(now: datetime, **overrides: object) -> ExchangeFlowObservation:
    fields: dict[str, object] = {
        "provider": "cryptoq",
        "provider_series_id": "btc-binance-inflow",
        "asset": "BTC",
        "network": "bitcoin",
        "exchange": "binance",
        "observation_time": now,
        "received_at": now,
        "inflow": Decimal("120.5"),
        "unit": OnChainUnit.NATIVE_ASSET,
    }
    fields.update(overrides)
    return ExchangeFlowObservation(**fields)


def test_required_fields_construct_a_valid_observation(now: datetime) -> None:
    observation = _observation(now)
    assert observation.exchange == "binance"
    assert observation.inflow == Decimal("120.5")


def test_exchange_none_means_provider_aggregate(now: datetime) -> None:
    observation = _observation(now, exchange=None)
    assert observation.exchange is None


def test_zero_flow_value_is_valid_not_missing(now: datetime) -> None:
    observation = _observation(now, inflow=Decimal("0"))
    assert observation.inflow == Decimal("0")
    assert observation.inflow is not None


def test_negative_inflow_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, inflow=Decimal("-1"))


def test_negative_outflow_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, inflow=None, outflow=Decimal("-1"), unit=OnChainUnit.NATIVE_ASSET)


def test_negative_balance_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, inflow=None, balance=Decimal("-1"), unit=OnChainUnit.NATIVE_ASSET)


def test_outflow_alone_is_sufficient(now: datetime) -> None:
    observation = _observation(now, inflow=None, outflow=Decimal("50"), unit=OnChainUnit.USD)
    assert observation.inflow is None
    assert observation.outflow == Decimal("50")


def test_balance_alone_is_sufficient(now: datetime) -> None:
    observation = _observation(now, inflow=None, balance=Decimal("2500000"), unit=OnChainUnit.NATIVE_ASSET)
    assert observation.balance == Decimal("2500000")


def test_at_least_one_flow_value_required(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, inflow=None, unit=None)


def test_unit_required_when_any_value_present(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unit=None)


def test_unit_forbidden_when_no_value_present(now: datetime) -> None:
    with pytest.raises(ValidationError):
        ExchangeFlowObservation(
            provider="cryptoq",
            provider_series_id="btc-binance-inflow",
            asset="BTC",
            network="bitcoin",
            exchange="binance",
            observation_time=now,
            received_at=now,
            unit=OnChainUnit.NATIVE_ASSET,
        )


def test_no_verification_or_confidence_fields_exist() -> None:
    """These are PROVIDER-CLASSIFIED facts, never independently verified -
    no such field may exist on this model."""
    forbidden = {"verified", "ground_truth", "confidence", "reliability", "classification_quality"}
    assert forbidden.isdisjoint(ExchangeFlowObservation.model_fields)


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unexpected_field="value")
