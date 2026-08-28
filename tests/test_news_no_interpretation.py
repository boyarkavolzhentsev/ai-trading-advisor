"""Stage 4C must never interpret news facts, and must never implement
sentiment, relevance, importance/ranking, market-impact, entity resolution
beyond provider metadata, cross-provider deduplication, semantic similarity,
clustering, narrative detection, or credibility/fake-news scoring - all
explicitly deferred per the approved Stage 4C design.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models.news_item import NewsItem
from app.news import exceptions, history, protocols, provenance

MODULES = (exceptions, history, protocols, provenance)
MODEL_CLASSES = (NewsItem,)

FORBIDDEN_TERMS = (
    "sentiment",
    "relevance",
    "importance",
    "market_impact",
    "fake",
    "cluster",
    "narrative",
    "similar",
    "duplicate_of",
    "canonical_story",
    "bullish",
    "bearish",
)
"""Deliberately excludes "reliability"/"credibility": both provenance
docstrings (here and in ``app.macro``/``app.rates``) legitimately explain
*why no such score exists* using that vocabulary in negation - enforcement
for those two belongs on ``FORBIDDEN_FIELDS`` (actual field names) below,
never on source-text scanning, mirroring why
``tests/test_rates_no_interpretation.py`` doesn't scan for them either."""

FORBIDDEN_FIELDS = {
    "sentiment_score",
    "relevance_score",
    "importance_score",
    "market_impact",
    "reliability_score",
    "credibility_score",
    "cluster_id",
    "canonical_story_id",
    "is_duplicate_of",
    "revision_number",
}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_interpretation_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_TERMS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden interpretation term(s): {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_no_interpretation_or_deferred_fields_on_models(model_cls) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(model_cls.model_fields)


def test_no_secret_shaped_fields_on_any_news_model() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for model_cls in MODEL_CLASSES:
        for field_name in model_cls.model_fields:
            lowered = field_name.lower()
            assert not any(term in lowered for term in forbidden_substrings), f"{model_cls.__name__}.{field_name}"


def test_no_revision_conflict_error_exists_in_news_exceptions() -> None:
    assert not hasattr(exceptions, "RevisionConflictError")


def test_no_single_god_news_provider_with_extra_capabilities_exists() -> None:
    """``NewsProvider`` must expose only ``get_news`` - no sentiment/relevance/
    entity-resolution capability bolted onto the same protocol."""
    method_names = [
        name
        for name, value in vars(protocols.NewsProvider).items()
        if not name.startswith("_") and callable(value)
    ]
    assert method_names == ["get_news"]


def test_no_quality_module_exists() -> None:
    """No universal staleness threshold, no ``is_stale`` field - see
    ``test_news_module_hygiene.py`` for the sibling file-existence check."""
    for model_cls in MODEL_CLASSES:
        assert "is_stale" not in model_cls.model_fields


def test_no_llm_summarized_body_field_exists() -> None:
    assert "summary" not in NewsItem.model_fields
    assert "generated_summary" not in NewsItem.model_fields
