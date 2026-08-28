"""Stage 4C ``NewsProvenance``/``NewsDataSource``."""

from __future__ import annotations

from datetime import datetime

from app.news.provenance import NewsDataSource, NewsProvenance


def test_label_combines_provider_and_source(now: datetime) -> None:
    provenance = NewsProvenance(provider="testnews", source=NewsDataSource.NEWS_FEED, fetched_at=now)
    assert provenance.label == "testnews:NEWS_FEED"


def test_provider_timestamp_and_source_url_are_optional(now: datetime) -> None:
    provenance = NewsProvenance(provider="testnews", source=NewsDataSource.NEWS_FEED, fetched_at=now)
    assert provenance.provider_timestamp is None
    assert provenance.source_url is None


def test_news_data_source_has_only_approved_member() -> None:
    assert {m.value for m in NewsDataSource} == {"NEWS_FEED"}


def test_provenance_has_no_reliability_or_confidence_field() -> None:
    forbidden = {"reliability", "confidence", "quality_score", "credibility"}
    assert forbidden.isdisjoint(NewsProvenance.model_fields)
