"""Stage 4E must never interpret on-chain facts, and must never implement
provider-native derived metrics (MVRV/SOPR/NVT/realized cap/whale metrics),
a generic metric-name/value bag, derived arithmetic (net flow, supply
change, rates of change, moving averages, z-scores, normalization,
composite scores), or any bullish/bearish/accumulation/distribution/
risk-on/risk-off/signal/recommendation/importance/market-impact/confidence/
reliability/credibility judgment - all explicitly deferred per the approved
Stage 4E design and its scope corrections.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.onchain import exceptions, history, protocols, provenance

MODULES = (exceptions, history, protocols, provenance)
MODEL_CLASSES = (
    NetworkActivityObservation,
    SupplyObservation,
    ExchangeFlowObservation,
    StablecoinSupplyObservation,
)

FORBIDDEN_TERMS = (
    "bullish",
    "bearish",
    "accumulation",
    "distribution",
    "risk_on",
    "risk_off",
    "risk-on",
    "risk-off",
    "buy_signal",
    "sell_signal",
    "recommendation",
    "market_impact",
    "mvrv",
    "sopr",
    "nvt",
    "realized_cap",
    "whale",
    "hash_rate",
    "difficulty",
    "staking",
    "bridge",
    "defi_tvl",
    "market_cap",
    "net_exchange_flow",
    "supply_change",
    "z_score",
    "moving_average",
    "cluster",
    "fake",
    "similar_to",
)
"""Deliberately excludes "confidence"/"reliability"/"credibility"/
"probability"/"importance"/"impact"/"verified"/"ground_truth"/"signal" as
blanket source-text terms: this package's own docstrings legitimately
explain *why no such thing exists* using that vocabulary in negation (see
``app.onchain.provenance``, ``app.core.models.exchange_flow_observation``) -
enforcement for those belongs on ``FORBIDDEN_FIELDS`` (actual schema
surface) below, never on blanket text scanning. Mirrors the identical fix
applied to ``tests/test_news_no_interpretation.py`` and
``tests/test_news_intel_no_interpretation.py``.

Also deliberately excludes "semantic": ``app.onchain.history`` legitimately
uses "semantic fingerprint"/"semantic duplicate detection" as established
repository vocabulary for the fingerprint-based deduplication mechanism -
unrelated to semantic text interpretation."""

FORBIDDEN_FIELDS = {
    "confidence",
    "reliability",
    "credibility",
    "probability",
    "importance",
    "impact",
    "verified",
    "ground_truth",
    "classification_quality",
    "signal",
    "recommendation",
    "direction",
    "origin",
    "revision_number",
    "metric_name",
    "metric_value",
    "value",
    "metric",
}
"""Includes "value"/"metric" (a generic metric-name/value bag field shape)
and "origin" (rejected for Stage 4E exactly as ``SentimentOrigin`` was
rejected for Stage 4D - every observation here is provider-native by
definition)."""


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_interpretation_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_TERMS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden interpretation term(s): {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_no_interpretation_or_deferred_fields_on_models(model_cls) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(model_cls.model_fields)


def test_no_secret_shaped_fields_on_any_onchain_model() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for model_cls in MODEL_CLASSES:
        for field_name in model_cls.model_fields:
            lowered = field_name.lower()
            assert not any(term in lowered for term in forbidden_substrings), f"{model_cls.__name__}.{field_name}"


def test_no_revision_conflict_error_exists_in_onchain_exceptions() -> None:
    assert not hasattr(exceptions, "RevisionConflictError")


def test_no_derived_metric_observation_model_exists() -> None:
    import app.core.models as core_models

    for forbidden in ("OnChainDerivedMetricObservation", "DerivedMetricObservation"):
        assert not hasattr(core_models, forbidden)


def test_no_derived_metric_enum_exists() -> None:
    import app.core.enums.onchain as onchain_enums

    for forbidden in ("OnChainDerivedMetric", "DerivedMetric"):
        assert not hasattr(onchain_enums, forbidden)


def test_no_generic_get_metric_provider_method_exists() -> None:
    method_names = {
        name for name, value in vars(protocols.OnChainProvider).items() if not name.startswith("_") and callable(value)
    }
    assert "get_metric" not in method_names
    assert "get_derived_metric" not in method_names


def test_no_quality_module_exists() -> None:
    for model_cls in MODEL_CLASSES:
        assert "is_stale" not in model_cls.model_fields


def test_enums_are_closed_to_approved_members_only() -> None:
    from app.core.enums.onchain import OnChainUnit

    assert {m.value for m in OnChainUnit} == {"NATIVE_ASSET", "USD"}
