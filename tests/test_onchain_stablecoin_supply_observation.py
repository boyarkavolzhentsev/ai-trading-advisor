"""Stage 4E ``StablecoinSupplyObservation`` model validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation


def _observation(now: datetime, **overrides: object) -> StablecoinSupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "usdt-eth-supply",
        "asset": "USDT",
        "network": "ethereum",
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("50000000000"),
    }
    fields.update(overrides)
    return StablecoinSupplyObservation(**fields)


def test_required_fields_construct_a_valid_observation(now: datetime) -> None:
    observation = _observation(now)
    assert observation.asset == "USDT"
    assert observation.network == "ethereum"


def test_same_asset_different_network_are_independent_identities(now: datetime) -> None:
    eth_usdt = _observation(now, asset="USDT", network="ethereum")
    tron_usdt = _observation(now, asset="USDT", network="tron")
    assert eth_usdt.asset == tron_usdt.asset
    assert eth_usdt.network != tron_usdt.network


def test_zero_mint_amount_is_valid_not_missing(now: datetime) -> None:
    observation = _observation(now, total_supply=None, mint_amount=Decimal("0"))
    assert observation.mint_amount == Decimal("0")
    assert observation.mint_amount is not None


def test_negative_total_supply_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=Decimal("-1"))


def test_negative_circulating_supply_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=None, circulating_supply=Decimal("-1"))


def test_negative_mint_amount_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=None, mint_amount=Decimal("-1"))


def test_negative_burn_amount_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, total_supply=None, burn_amount=Decimal("-1"))


def test_mint_amount_alone_is_sufficient(now: datetime) -> None:
    observation = _observation(now, total_supply=None, mint_amount=Decimal("1000000"))
    assert observation.mint_amount == Decimal("1000000")


def test_burn_amount_alone_is_sufficient(now: datetime) -> None:
    observation = _observation(now, total_supply=None, burn_amount=Decimal("500000"))
    assert observation.burn_amount == Decimal("500000")


def test_at_least_one_value_required(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(
            now,
            total_supply=None,
            circulating_supply=None,
            mint_amount=None,
            burn_amount=None,
        )


def test_no_unit_field_exists() -> None:
    assert "unit" not in StablecoinSupplyObservation.model_fields


def test_no_liquidity_or_risk_condition_fields_exist() -> None:
    forbidden = {"liquidity_condition", "risk_on", "risk_off", "liquidity_score"}
    assert forbidden.isdisjoint(StablecoinSupplyObservation.model_fields)


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unexpected_field="value")
