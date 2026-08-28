"""Stage 4D ``NewsSentimentObservation`` model validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.models.news_sentiment_observation import NewsSentimentObservation


def _observation(now: datetime, **overrides: object) -> NewsSentimentObservation:
    fields: dict[str, object] = {
        "provider": "sentvendor",
        "source_provider": "testnews",
        "source_provider_item_id": "story-1",
        "source_received_at": now,
        "published_at": now,
        "received_at": now,
        "sentiment_label": "positive",
    }
    fields.update(overrides)
    return NewsSentimentObservation(**fields)


def test_required_fields_construct_a_valid_observation(now: datetime) -> None:
    observation = _observation(now)
    assert observation.provider == "sentvendor"
    assert observation.source_provider == "testnews"
    assert observation.source_provider_item_id == "story-1"


def test_target_symbol_defaults_to_none_meaning_whole_item(now: datetime) -> None:
    observation = _observation(now)
    assert observation.target_symbol is None


def test_target_symbol_can_be_set_for_per_entity_sentiment(now: datetime) -> None:
    observation = _observation(now, target_symbol="BTCUSDT")
    assert observation.target_symbol == "BTCUSDT"


def test_sentiment_score_is_decimal_not_float(now: datetime) -> None:
    observation = _observation(now, sentiment_score=Decimal("0.73"))
    assert isinstance(observation.sentiment_score, Decimal)
    assert observation.sentiment_score == Decimal("0.73")


def test_decimal_sentiment_score_is_preserved_exactly(now: datetime) -> None:
    """No rescaling/normalization: the exact provider-reported Decimal survives round-trip."""
    exact = Decimal("0.123456789012345")
    observation = _observation(now, sentiment_score=exact)
    assert observation.sentiment_score == exact
    assert str(observation.sentiment_score) == str(exact)


def test_negative_sentiment_score_is_valid(now: datetime) -> None:
    observation = _observation(now, sentiment_score=Decimal("-0.85"))
    assert observation.sentiment_score == Decimal("-0.85")


def test_zero_sentiment_score_is_a_valid_fact_not_missing(now: datetime) -> None:
    observation = _observation(now, sentiment_label=None, sentiment_score=Decimal("0"))
    assert observation.sentiment_score == Decimal("0")
    assert observation.sentiment_score is not None


def test_out_of_conventional_range_sentiment_score_is_not_rejected(now: datetime) -> None:
    """No canonical bounds are imposed - a provider's own scale may exceed [-1, 1]."""
    observation = _observation(now, sentiment_label=None, sentiment_score=Decimal("87.5"))
    assert observation.sentiment_score == Decimal("87.5")


def test_sentiment_scale_is_free_text_and_optional(now: datetime) -> None:
    observation = _observation(now, sentiment_score=Decimal("0.5"), sentiment_scale="0 to 1")
    assert observation.sentiment_scale == "0 to 1"
    without_scale = _observation(now, sentiment_score=Decimal("0.5"))
    assert without_scale.sentiment_scale is None


def test_sentiment_label_preserved_verbatim(now: datetime) -> None:
    observation = _observation(now, sentiment_label="somewhat_bullish_ish")
    assert observation.sentiment_label == "somewhat_bullish_ish"


def test_at_least_one_of_label_or_score_is_required(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, sentiment_label=None, sentiment_score=None)


def test_label_only_is_sufficient(now: datetime) -> None:
    observation = _observation(now, sentiment_label="positive", sentiment_score=None)
    assert observation.sentiment_score is None


def test_score_only_is_sufficient(now: datetime) -> None:
    observation = _observation(now, sentiment_label=None, sentiment_score=Decimal("0.4"))
    assert observation.sentiment_label is None


def test_model_has_no_origin_field() -> None:
    """Required correction: no SentimentOrigin, no origin field at all -
    every record here is provider-native by definition."""
    assert "origin" not in NewsSentimentObservation.model_fields


def test_model_is_frozen(now: datetime) -> None:
    observation = _observation(now)
    with pytest.raises(ValidationError):
        observation.sentiment_label = "changed"  # type: ignore[misc]


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, unexpected_field="value")


def test_naive_datetime_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _observation(now, published_at=datetime(2026, 1, 1))
