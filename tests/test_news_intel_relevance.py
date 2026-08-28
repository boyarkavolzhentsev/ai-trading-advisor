"""Stage 4D ``compute_relevance`` deterministic transform."""

from __future__ import annotations

from datetime import datetime, timedelta



import pytest
from pydantic import ValidationError

from app.core.enums.news_intel import RelevanceMethod
from app.core.enums.quality import FeatureQuality
from app.core.models.news_item import NewsItem
from app.core.models.news_relevance_observation import NewsRelevanceObservation
from app.news_intel.relevance import compute_relevance


def _item(now: datetime, **overrides: object) -> NewsItem:
    fields: dict[str, object] = {
        "provider": "testnews",
        "provider_item_id": "story-1",
        "headline": "Central bank holds rates steady",
        "published_at": now,
        "received_at": now,
    }
    fields.update(overrides)
    return NewsItem(**fields)


def test_exact_match_is_a_valid_positive(now: datetime) -> None:
    item = _item(now, provider_symbols=["BTCUSDT", "ETHUSDT"])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.matched is True
    assert result.quality is FeatureQuality.VALID


def test_checked_negative_is_valid_and_not_matched(now: datetime) -> None:
    """A genuine checked negative: provider_symbols present, none match."""
    item = _item(now, provider_symbols=["ETHUSDT"])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.matched is False
    assert result.quality is FeatureQuality.VALID


def test_empty_provider_symbols_is_unavailable_not_a_negative(now: datetime) -> None:
    """Distinct from the checked negative above: no data to check at all."""
    item = _item(now, provider_symbols=[])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.matched is False
    assert result.quality is FeatureQuality.UNAVAILABLE


def test_valid_negative_and_unavailable_negative_are_structurally_distinct(now: datetime) -> None:
    checked_negative = compute_relevance(_item(now, provider_symbols=["ETHUSDT"]), "BTCUSDT", now)
    no_data = compute_relevance(_item(now, provider_symbols=[]), "BTCUSDT", now)
    assert checked_negative.matched == no_data.matched == False  # noqa: E712
    assert checked_negative.quality != no_data.quality


def test_method_is_provider_symbol_exact_match(now: datetime) -> None:
    item = _item(now, provider_symbols=["BTCUSDT"])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.method is RelevanceMethod.PROVIDER_SYMBOL_EXACT_MATCH


def test_evidence_linkage_cites_the_source_item_exactly(now: datetime) -> None:
    item = _item(now, provider="testnews", provider_item_id="story-42", provider_symbols=["BTCUSDT"])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.source_provider == item.provider
    assert result.source_provider_item_id == item.provider_item_id
    assert result.source_received_at == item.received_at


def test_computed_at_is_caller_supplied_not_wall_clock(now: datetime) -> None:
    item = _item(now, provider_symbols=["BTCUSDT"])
    later = now + timedelta(hours=3)
    result = compute_relevance(item, "BTCUSDT", later)
    assert result.computed_at == later


def test_deterministic_repeatability(now: datetime) -> None:
    item = _item(now, provider_symbols=["BTCUSDT"])
    first = compute_relevance(item, "BTCUSDT", now)
    second = compute_relevance(item, "BTCUSDT", now)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_no_text_parsing_headline_mention_does_not_match(now: datetime) -> None:
    """No keyword/text matching: a symbol mentioned only in the headline,
    absent from provider_symbols, must not match."""
    item = _item(now, headline="BTCUSDT rallies on ETF inflows", provider_symbols=[])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.matched is False
    assert result.quality is FeatureQuality.UNAVAILABLE


def test_no_provider_tags_interpretation(now: datetime) -> None:
    """No tag interpretation: a matching provider_tags entry must not
    substitute for a provider_symbols match."""
    item = _item(now, provider_tags=["BTCUSDT"], provider_symbols=[])
    result = compute_relevance(item, "BTCUSDT", now)
    assert result.matched is False
    assert result.quality is FeatureQuality.UNAVAILABLE


def test_matched_true_requires_valid_quality(now: datetime) -> None:
    with pytest.raises(ValidationError):
        NewsRelevanceObservation(
            source_provider="testnews",
            source_provider_item_id="story-1",
            source_received_at=now,
            symbol="BTCUSDT",
            matched=True,
            quality=FeatureQuality.UNAVAILABLE,
            method=RelevanceMethod.PROVIDER_SYMBOL_EXACT_MATCH,
            computed_at=now,
        )
