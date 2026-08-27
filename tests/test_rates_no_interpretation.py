"""Stage 4B must never interpret rates/yields facts, and must never implement
yield spreads, DXY/currency-index facts, or liquidity series - all
explicitly deferred per the approved Stage 4B design.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.enums.rates import GovernmentYieldType, PolicyRateKind, SeriesUnit, TenorUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor
from app.rates import exceptions, history, protocols, provenance

MODULES = (exceptions, history, protocols, provenance)
MODEL_CLASSES = (PolicyRateObservation, GovernmentYieldObservation, Tenor)

FORBIDDEN_TERMS = (
    "hawkish",
    "dovish",
    "bullish",
    "bearish",
    "risk-on",
    "risk_on",
    "risk-off",
    "risk_off",
    "invert",
    "recession",
    "trend",
    "rising",
    "falling",
    "regime",
    "btc_relevance",
    "cross_asset",
    "rate_impact",
    "yield_impact",
)

FORBIDDEN_FIELDS = {
    "spread",
    "spread_value",
    "curve_state",
    "is_inverted",
    "inversion",
    "dxy",
    "index_value",
    "liquidity",
    "is_stale",
}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_interpretation_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_TERMS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden interpretation term(s): {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_no_interpretation_or_deferred_fields_on_models(model_cls) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(model_cls.model_fields)


def test_no_secret_shaped_fields_on_any_rates_model() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for model_cls in MODEL_CLASSES:
        for field_name in model_cls.model_fields:
            lowered = field_name.lower()
            assert not any(term in lowered for term in forbidden_substrings), f"{model_cls.__name__}.{field_name}"


def test_no_spread_calculation_helper_defined_anywhere_in_rates() -> None:
    forbidden_names = {"spread", "compute_spread", "yield_spread", "curve_spread", "derive_spread"}
    for module in MODULES:
        defined_names = {
            name for name, value in vars(module).items() if inspect.isfunction(value) or inspect.isclass(value)
        }
        assert forbidden_names.isdisjoint({n.lower() for n in defined_names})


def test_no_dxy_or_currency_index_model_exists() -> None:
    import app.core.models as core_models

    for forbidden in ("CurrencyIndexObservation", "DXYObservation"):
        assert not hasattr(core_models, forbidden)


def test_no_liquidity_model_exists() -> None:
    import app.core.models as core_models

    for forbidden in (
        "BalanceSheetObservation",
        "ReverseRepoObservation",
        "LiquidityObservation",
        "MoneySupplyObservation",
        "StablecoinSupplyObservation",
    ):
        assert not hasattr(core_models, forbidden)


def test_no_index_points_unit_exists() -> None:
    """``INDEX_POINTS`` is deliberately absent: no series in Stage 4B's
    approved scope uses it, and adding it would imply DXY support."""
    assert "INDEX_POINTS" not in {member.name for member in SeriesUnit}


def test_no_single_god_rates_provider_exists() -> None:
    assert not hasattr(protocols, "RatesProvider")


def test_no_quality_module_exists() -> None:
    """No universal staleness threshold, no ``is_stale`` field - see
    ``test_rates_module_hygiene.py`` for the sibling file-existence check."""
    for model_cls in MODEL_CLASSES:
        assert "is_stale" not in model_cls.model_fields


def test_enums_are_closed_to_approved_members_only() -> None:
    assert {m.value for m in PolicyRateKind} == {"TARGET", "TARGET_LOWER", "TARGET_UPPER", "EFFECTIVE"}
    assert {m.value for m in GovernmentYieldType} == {"NOMINAL", "REAL"}
    assert {m.value for m in SeriesUnit} == {"PERCENT", "BASIS_POINTS"}
    assert {m.value for m in TenorUnit} == {"MONTHS", "YEARS"}
