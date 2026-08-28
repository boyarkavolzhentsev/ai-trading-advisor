"""Stage 4D ``NewsIntelProvenance``/``NewsIntelDataSource``."""

from __future__ import annotations

from datetime import datetime

from app.news_intel.provenance import NewsIntelDataSource, NewsIntelProvenance


def test_label_combines_provider_and_source(now: datetime) -> None:
    provenance = NewsIntelProvenance(provider="sentvendor", source=NewsIntelDataSource.SENTIMENT_FEED, fetched_at=now)
    assert provenance.label == "sentvendor:SENTIMENT_FEED"


def test_provider_timestamp_and_source_url_are_optional(now: datetime) -> None:
    provenance = NewsIntelProvenance(provider="sentvendor", source=NewsIntelDataSource.SENTIMENT_FEED, fetched_at=now)
    assert provenance.provider_timestamp is None
    assert provenance.source_url is None


def test_news_intel_data_source_has_only_approved_member() -> None:
    assert {m.value for m in NewsIntelDataSource} == {"SENTIMENT_FEED"}


def test_provenance_has_no_confidence_reliability_credibility_or_ranking_field() -> None:
    forbidden = {"confidence", "reliability", "credibility", "probability", "provider_ranking", "quality_score"}
    assert forbidden.isdisjoint(NewsIntelProvenance.model_fields)
