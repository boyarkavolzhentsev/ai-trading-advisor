"""Stage 4D must never interpret news facts, and must never implement
internally-derived sentiment, lexicon/text-based sentiment, numeric
relevance scoring, importance/priority/market-impact, asset-class or
macro-theme relevance, keyword/tag relevance, fuzzy/semantic matching,
cross-provider reconciliation, entity resolution beyond exact provider
symbols, recency weighting, or credibility/reliability/confidence scoring -
all explicitly deferred per the approved Stage 4D design.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models.news_relevance_observation import NewsRelevanceObservation
from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.news_intel import exceptions, provenance, relevance, sentiment_history, sentiment_protocol

MODULES = (exceptions, provenance, relevance, sentiment_history, sentiment_protocol)
MODEL_CLASSES = (NewsRelevanceObservation, NewsSentimentObservation)

FORBIDDEN_TERMS = (
    "sentiment_score_normalized",
    "market_impact",
    "fake",
    "cluster",
    "narrative",
    "similar",
    "duplicate_of",
    "canonical_story",
    "bullish",
    "bearish",
    "keyword",
    "fuzzy",
    "recency_weight",
    "decay",
    "provider_ranking",
)
"""Deliberately excludes "importance"/"impact"/"priority"/"reliability"/
"credibility"/"confidence" as blanket source-text terms: this package's own
docstrings legitimately explain *why no such thing exists* using that
vocabulary in negation (see ``app.core.enums.news_intel``,
``app.news_intel.provenance``) - enforcement for those belongs on
``FORBIDDEN_FIELDS``/``FORBIDDEN_ENUM_MEMBERS`` (actual schema surface)
below, never on blanket text scanning. Mirrors the same fix applied to
``tests/test_news_no_interpretation.py`` after the Stage 4C review.

Also deliberately excludes "semantic": ``app.news.history`` and
``app.news_intel.sentiment_history`` legitimately use "semantic
fingerprint"/"semantic duplicate detection" as established vocabulary for
the fingerprint-based deduplication mechanism (excluding ``received_at``
from comparison) - unrelated to semantic *text* matching, which "similar"
already covers below."""

FORBIDDEN_FIELDS = {
    "importance",
    "priority",
    "market_impact",
    "reliability_score",
    "credibility_score",
    "confidence",
    "confidence_score",
    "cluster_id",
    "canonical_story_id",
    "is_duplicate_of",
    "origin",
    "revision_number",
    "relevance_score",
}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_interpretation_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_TERMS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden interpretation term(s): {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_no_interpretation_or_deferred_fields_on_models(model_cls) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(model_cls.model_fields)


def test_no_secret_shaped_fields_on_any_news_intel_model() -> None:
    forbidden_substrings = ("key", "secret", "token", "password", "credential")
    for model_cls in MODEL_CLASSES:
        for field_name in model_cls.model_fields:
            lowered = field_name.lower()
            assert not any(term in lowered for term in forbidden_substrings), f"{model_cls.__name__}.{field_name}"


def test_no_revision_conflict_error_exists_in_news_intel_exceptions() -> None:
    assert not hasattr(exceptions, "RevisionConflictError")


def test_no_single_god_sentiment_provider_with_extra_capabilities_exists() -> None:
    method_names = [
        name
        for name, value in vars(sentiment_protocol.NewsSentimentProvider).items()
        if not name.startswith("_") and callable(value)
    ]
    assert method_names == ["get_sentiment"]


def test_no_quality_module_exists() -> None:
    for model_cls in MODEL_CLASSES:
        assert "is_stale" not in model_cls.model_fields


def test_no_llm_summarized_field_exists() -> None:
    for model_cls in MODEL_CLASSES:
        assert "summary" not in model_cls.model_fields
        assert "generated_summary" not in model_cls.model_fields


def test_no_sentiment_origin_enum_or_field_exists() -> None:
    """Required correction: do not pre-design an INTERNALLY_DERIVED enum
    member or schema path now."""
    import app.core.enums.news_intel as news_intel_enums

    assert not hasattr(news_intel_enums, "SentimentOrigin")
    assert "origin" not in NewsSentimentObservation.model_fields


def test_no_analysis_dimension_or_analyst_outcome_vocabulary_referenced() -> None:
    """No AnalysisDimension/AnalystOutcome-shaped output: Stage 4D produces
    facts, not analyst observations - that is Stage 4F's job."""
    forbidden_names = ("AnalysisDimension", "AnalystOutcome", "AnalystType", "AgentAssessment")
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        for forbidden in forbidden_names:
            assert forbidden not in source, f"{module.__name__} references forbidden name {forbidden!r}"


def test_no_aggregation_across_analysts_function_exists() -> None:
    """No supervisor-shaped behavior anywhere in this package."""
    forbidden_names = {"aggregate", "supervise", "rank_by_importance", "prioritize"}
    for module in MODULES:
        defined_names = {
            name for name, value in vars(module).items() if inspect.isfunction(value) or inspect.isclass(value)
        }
        assert forbidden_names.isdisjoint({n.lower() for n in defined_names})


def test_enums_are_closed_to_approved_members_only() -> None:
    from app.core.enums.news_intel import RelevanceMethod
    from app.news_intel.provenance import NewsIntelDataSource

    assert {m.value for m in RelevanceMethod} == {"PROVIDER_SYMBOL_EXACT_MATCH"}
    assert {m.value for m in NewsIntelDataSource} == {"SENTIMENT_FEED"}
