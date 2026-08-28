"""Stage 4F ``NewsSentimentAnalyst`` deterministic calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RelevantItemPresence,
    SentimentAgreementVerdict,
    SentimentSign,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.news_item import NewsItem
from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.external_intelligence_analysts import NewsSentimentAnalyst, NewsSentimentAnalystConfig

CONFIG = NewsSentimentAnalystConfig(recency_window=timedelta(hours=24), staleness_threshold=timedelta(hours=24))
SYMBOL = "BTCUSDT"


def _item(now: datetime, **overrides: object) -> NewsItem:
    fields: dict[str, object] = {
        "provider": "newsfeed",
        "provider_item_id": "story-1",
        "headline": "Central bank holds rates steady",
        "published_at": now,
        "received_at": now,
        "provider_symbols": [SYMBOL],
    }
    fields.update(overrides)
    return NewsItem(**fields)


def _sentiment(item: NewsItem, **overrides: object) -> NewsSentimentObservation:
    fields: dict[str, object] = {
        "provider": "sentvendorA",
        "source_provider": item.provider,
        "source_provider_item_id": item.provider_item_id,
        "source_received_at": item.received_at,
        "published_at": item.published_at,
        "sentiment_score": Decimal("0.5"),
        "received_at": item.received_at,
    }
    fields.update(overrides)
    return NewsSentimentObservation(**fields)


def _dims(result, dimension: ExternalIntelligenceDimension):
    return [o for o in result.observations if o.dimension is dimension]


def test_abstains_with_no_news_items(now: datetime) -> None:
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_exact_relevance_match(now: datetime) -> None:
    item = _item(now, provider_symbols=[SYMBOL])
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    presence = _dims(result, ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE)
    assert presence[0].value == RelevantItemPresence.ITEMS_FOUND.value


def test_no_relevance_match_for_different_symbol(now: datetime) -> None:
    item = _item(now, provider_symbols=["ETHUSDT"])
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    presence = _dims(result, ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE)
    assert presence[0].value == RelevantItemPresence.NO_ITEMS.value


def test_undetermined_relevance_omits_presence_and_abstains(now: datetime) -> None:
    """No provider_symbols at all means relevance quality is UNAVAILABLE -
    this must never be treated as evidence of RELEVANT_ITEM_PRESENCE=NO_ITEMS."""
    item = _item(now, provider_symbols=[])
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_relevance_recency_uses_published_at_not_received_at(now: datetime) -> None:
    item = _item(now, published_at=now - timedelta(hours=1), received_at=now - timedelta(days=100))
    sentiment = _sentiment(item)
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert len(signs) == 1  # recency window judged from published_at (1h old), not received_at (100d old)


def test_item_outside_recency_window_excluded_from_sentiment(now: datetime) -> None:
    item = _item(now, published_at=now - timedelta(days=10))
    sentiment = _sentiment(item)
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN) == []
    # still contributes to relevant-item presence
    presence = _dims(result, ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE)
    assert presence[0].value == RelevantItemPresence.ITEMS_FOUND.value


def test_provider_positive_sign(now: datetime) -> None:
    item = _item(now)
    sentiment = _sentiment(item, sentiment_score=Decimal("0.7"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert signs[0].value == SentimentSign.POSITIVE.value


def test_provider_negative_sign(now: datetime) -> None:
    item = _item(now)
    sentiment = _sentiment(item, sentiment_score=Decimal("-0.4"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert signs[0].value == SentimentSign.NEGATIVE.value


def test_provider_zero_sign_is_a_real_value_not_missing(now: datetime) -> None:
    item = _item(now)
    sentiment = _sentiment(item, sentiment_score=Decimal("0"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert signs[0].value == SentimentSign.ZERO.value


def test_provider_mixed_when_own_items_disagree(now: datetime) -> None:
    item1 = _item(now, provider_item_id="story-1")
    item2 = _item(now, provider_item_id="story-2")
    pos = _sentiment(item1, sentiment_score=Decimal("0.5"))
    neg = _sentiment(item2, sentiment_score=Decimal("-0.5"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item1, item2], [pos, neg], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert signs[0].value == SentimentSign.MIXED.value


def test_provider_agreement_all_agree(now: datetime) -> None:
    item1 = _item(now, provider_item_id="story-1")
    item2 = _item(now, provider_item_id="story-2")
    s1 = _sentiment(item1, provider="vendorA", sentiment_score=Decimal("0.5"))
    s2 = _sentiment(item2, provider="vendorB", sentiment_score=Decimal("0.8"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item1, item2], [s1, s2], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    agreement = _dims(result, ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT)
    assert agreement[0].value == SentimentAgreementVerdict.ALL_AGREE.value


def test_provider_disagreement_mixed(now: datetime) -> None:
    item1 = _item(now, provider_item_id="story-1")
    item2 = _item(now, provider_item_id="story-2")
    s1 = _sentiment(item1, provider="vendorA", sentiment_score=Decimal("0.5"))
    s2 = _sentiment(item2, provider="vendorB", sentiment_score=Decimal("-0.5"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item1, item2], [s1, s2], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    agreement = _dims(result, ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT)
    assert agreement[0].value == SentimentAgreementVerdict.MIXED.value


def test_provider_agreement_insufficient_data_with_one_provider(now: datetime) -> None:
    item = _item(now)
    sentiment = _sentiment(item, sentiment_score=Decimal("0.5"))
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    agreement = _dims(result, ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT)
    assert agreement[0].value == SentimentAgreementVerdict.INSUFFICIENT_DATA.value


def test_missing_sentiment_is_not_neutral(now: datetime) -> None:
    """A relevant item with no sentiment observation at all must never
    fabricate a ZERO/neutral sentiment sign."""
    item = _item(now)
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN) == []
    assert _dims(result, ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT) == []
    presence = _dims(result, ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE)
    assert presence[0].value == RelevantItemPresence.ITEMS_FOUND.value


def test_incompatible_provider_scales_never_averaged(now: datetime) -> None:
    """Two providers on wildly different numeric scales are never blended
    into one number - only their independent signs are compared."""
    item1 = _item(now, provider_item_id="story-1")
    item2 = _item(now, provider_item_id="story-2")
    s1 = _sentiment(item1, provider="vendorA", sentiment_score=Decimal("0.01"))  # tiny positive on a [-1,1] scale
    s2 = _sentiment(item2, provider="vendorB", sentiment_score=Decimal("87.5"))  # large positive on an unbounded scale
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item1, item2], [s1, s2], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    signs = _dims(result, ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN)
    assert {s.value for s in signs} == {SentimentSign.POSITIVE.value}
    agreement = _dims(result, ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT)
    assert agreement[0].value == SentimentAgreementVerdict.ALL_AGREE.value
    # no averaged/blended numeric value appears anywhere in evidence
    for e in result.evidence:
        assert e.observed_value not in {"43.755", "43.76"}


def test_no_partial_quality_ever_emitted(now: datetime) -> None:
    item = _item(now)
    sentiment = _sentiment(item)
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [sentiment], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    for observation in result.observations:
        assert observation.quality is not FeatureQuality.PARTIAL


def test_result_scope_is_symbol_only(now: datetime) -> None:
    item = _item(now)
    analyst = NewsSentimentAnalyst()
    result = analyst.analyze([item], [], symbol=SYMBOL, analysis_time=now, config=CONFIG)
    assert result.symbol == SYMBOL
    assert result.currency is None
    assert result.asset is None
    assert result.network is None
