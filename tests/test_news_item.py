"""Stage 4C ``NewsItem`` model validation.

``published_at``/``updated_at`` are independent, unrelated provider facts -
see ``app.core.models.news_item`` module docstring. This suite explicitly
confirms no chronological relationship between them is enforced: an item
whose ``updated_at`` precedes its ``published_at`` must construct without
error, exactly preserving both timestamps as supplied.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.models.news_item import NewsItem


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


def test_required_fields_construct_a_valid_item(now: datetime) -> None:
    item = _item(now)
    assert item.provider == "testnews"
    assert item.provider_item_id == "story-1"
    assert item.headline == "Central bank holds rates steady"
    assert item.published_at == now
    assert item.received_at == now


def test_optional_fields_default_to_none_or_empty(now: datetime) -> None:
    item = _item(now)
    assert item.body is None
    assert item.source is None
    assert item.source_url is None
    assert item.language is None
    assert item.updated_at is None
    assert item.provider_tags == []
    assert item.provider_symbols == []


def test_optional_fields_can_be_supplied(now: datetime) -> None:
    item = _item(
        now,
        body="The central bank left its policy rate unchanged at 4.25%.",
        source="Reuters",
        source_url="https://example.com/story-1",
        language="en",
        updated_at=now + timedelta(minutes=5),
        provider_tags=["central-banks", "rates"],
        provider_symbols=["EURUSD", "DXY"],
    )
    assert item.body == "The central bank left its policy rate unchanged at 4.25%."
    assert item.source == "Reuters"
    assert item.source_url == "https://example.com/story-1"
    assert item.language == "en"
    assert item.updated_at == now + timedelta(minutes=5)
    assert item.provider_tags == ["central-banks", "rates"]
    assert item.provider_symbols == ["EURUSD", "DXY"]


@pytest.mark.parametrize("field_name", ["provider", "provider_item_id", "headline"])
def test_required_string_fields_reject_empty_string(now: datetime, field_name: str) -> None:
    with pytest.raises(ValidationError):
        _item(now, **{field_name: ""})


@pytest.mark.parametrize("field_name", ["body", "source", "source_url", "language"])
def test_optional_string_fields_reject_empty_string(now: datetime, field_name: str) -> None:
    with pytest.raises(ValidationError):
        _item(now, **{field_name: ""})


def test_updated_at_before_published_at_is_accepted_and_preserved(now: datetime) -> None:
    """Required correction: Stage 4C must not enforce updated_at >= published_at.

    Both timestamps are independent provider facts; an out-of-order pair
    must construct without error and be preserved exactly as supplied.
    """
    earlier = now - timedelta(days=1)
    item = _item(now, published_at=now, updated_at=earlier)
    assert item.published_at == now
    assert item.updated_at == earlier


def test_updated_at_equal_to_published_at_is_accepted(now: datetime) -> None:
    item = _item(now, published_at=now, updated_at=now)
    assert item.updated_at == item.published_at


def test_updated_at_after_published_at_is_accepted(now: datetime) -> None:
    later = now + timedelta(hours=2)
    item = _item(now, published_at=now, updated_at=later)
    assert item.updated_at == later


def test_naive_datetime_is_rejected(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _item(now, published_at=datetime(2026, 1, 1))


def test_model_is_frozen(now: datetime) -> None:
    item = _item(now)
    with pytest.raises(ValidationError):
        item.headline = "Changed headline"  # type: ignore[misc]


def test_model_forbids_unknown_fields(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _item(now, unexpected_field="value")


def test_provider_tags_and_symbols_are_never_none() -> None:
    assert NewsItem.model_fields["provider_tags"].default_factory is not None
    assert NewsItem.model_fields["provider_symbols"].default_factory is not None
