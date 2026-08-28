"""Stage 4E ``OnChainProvenance``/``OnChainDataSource``."""

from __future__ import annotations

from datetime import datetime

from app.onchain.provenance import OnChainDataSource, OnChainProvenance


def test_label_combines_provider_and_source(now: datetime) -> None:
    provenance = OnChainProvenance(provider="glassnode", source=OnChainDataSource.NETWORK_ACTIVITY, fetched_at=now)
    assert provenance.label == "glassnode:NETWORK_ACTIVITY"


def test_provider_timestamp_and_source_url_are_optional(now: datetime) -> None:
    provenance = OnChainProvenance(provider="glassnode", source=OnChainDataSource.SUPPLY, fetched_at=now)
    assert provenance.provider_timestamp is None
    assert provenance.source_url is None


def test_data_source_has_exactly_four_approved_members() -> None:
    assert {m.value for m in OnChainDataSource} == {
        "NETWORK_ACTIVITY",
        "SUPPLY",
        "EXCHANGE_FLOW",
        "STABLECOIN_SUPPLY",
    }


def test_no_derived_metric_source_member_exists() -> None:
    assert "DERIVED_METRIC" not in {m.name for m in OnChainDataSource}


def test_provenance_has_no_confidence_reliability_credibility_importance_or_origin_field() -> None:
    forbidden = {
        "confidence",
        "reliability",
        "credibility",
        "probability",
        "importance",
        "impact",
        "origin",
    }
    assert forbidden.isdisjoint(OnChainProvenance.model_fields)
