"""Determinism: identical inputs produce identical, order-independent results."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.core.models.news_item import NewsItem
from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.news_intel.relevance import compute_relevance


def _item(now: datetime, **overrides: object) -> NewsItem:
    fields: dict[str, object] = {
        "provider": "testnews",
        "provider_item_id": "story-1",
        "headline": "Central bank holds rates steady",
        "published_at": now,
        "received_at": now,
        "provider_symbols": ["BTCUSDT"],
    }
    fields.update(overrides)
    return NewsItem(**fields)


def test_relevance_computation_is_deterministic(now: datetime) -> None:
    item = _item(now)
    first = compute_relevance(item, "BTCUSDT", now)
    second = compute_relevance(item, "BTCUSDT", now)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_sentiment_model_construction_is_deterministic(now: datetime) -> None:
    fields = dict(
        provider="sentvendor",
        source_provider="testnews",
        source_provider_item_id="story-1",
        source_received_at=now,
        published_at=now,
        received_at=now,
        sentiment_score=Decimal("0.42"),
    )
    first = NewsSentimentObservation(**fields)
    second = NewsSentimentObservation(**fields)
    assert first == second
    assert first.model_dump() == second.model_dump()
