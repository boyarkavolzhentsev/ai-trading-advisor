"""``FinalRecommendationProvenance`` field validation (Final Runtime
Integration, Part E corrective design)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance


def _build(**overrides: object) -> FinalRecommendationProvenance:
    fields: dict[str, object] = {
        "trade_id": "trade-1",
        "family": StrategyFamily.TREND_FOLLOWING,
        "approved_risk_amount": Decimal("120.50"),
        "account_currency": "DKK",
    }
    fields.update(overrides)
    return FinalRecommendationProvenance(**fields)


def test_valid_provenance_fields_unchanged() -> None:
    provenance = _build()
    assert provenance.trade_id == "trade-1"
    assert provenance.family is StrategyFamily.TREND_FOLLOWING
    assert provenance.approved_risk_amount == Decimal("120.50")
    assert provenance.account_currency == "DKK"


def test_empty_trade_id_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(trade_id="")


def test_zero_approved_risk_amount_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(approved_risk_amount=Decimal("0"))


def test_negative_approved_risk_amount_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(approved_risk_amount=Decimal("-5"))


def test_empty_account_currency_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(account_currency="")


def test_provenance_is_immutable() -> None:
    provenance = _build()
    with pytest.raises(ValidationError):
        provenance.family = StrategyFamily.BREAKOUT


def test_no_extra_fields_allowed() -> None:
    with pytest.raises(ValidationError):
        _build(symbol="EURUSD")


def test_no_market_field_exists() -> None:
    """Provenance is deliberately narrower than ``PositionRecord``: it must
    never carry ``market`` - that fact belongs only to Stage 10E's own
    tracking-creation call, never duplicated here."""
    assert "market" not in FinalRecommendationProvenance.model_fields


def test_no_approved_volume_or_setup_fields_duplicated() -> None:
    """Fields that already survive unchanged through ``PositionRecord``/
    ``MT5TrackedRecommendation`` must never be duplicated in provenance."""
    duplicated_fields = {
        "symbol",
        "direction",
        "entry_price",
        "stop_loss",
        "take_profit_levels",
        "approved_volume",
        "signal_time",
        "valid_until",
    }
    assert duplicated_fields.isdisjoint(FinalRecommendationProvenance.model_fields)
