"""Stage 4D must contain zero LLM dependency: no semantic classification,
summarization, sentiment inference from text, relevance inference beyond
exact symbol matching, or structured extraction by a model.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models import news_relevance_observation, news_sentiment_observation
from app.news_intel import exceptions, provenance, relevance, sentiment_history, sentiment_protocol

MODULES = (
    exceptions,
    provenance,
    relevance,
    sentiment_history,
    sentiment_protocol,
    news_relevance_observation,
    news_sentiment_observation,
)

FORBIDDEN_SUBSTRINGS = (
    "openai",
    "anthropic",
    "llm",
    "gpt",
    "claude",
    "prompt",
    "embedding",
    "language_model",
    "chat_completion",
    "summariz",
    "lexicon",
    "nlp",
)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_SUBSTRINGS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden LLM-adjacent term(s): {offenders}"


def test_no_third_party_llm_import_anywhere_in_news_intel_package() -> None:
    import app.news_intel as news_intel_package

    package_dir = Path(inspect.getfile(news_intel_package)).parent
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for term in ("openai", "anthropic", "langchain"):
            assert term not in source, f"{path} references forbidden LLM package {term!r}"


def test_no_http_client_import_anywhere_in_news_intel_package() -> None:
    """No real provider adapter/HTTP integration exists in Stage 4D."""
    import ast

    import app.news_intel as news_intel_package

    package_dir = Path(inspect.getfile(news_intel_package)).parent
    forbidden = {"requests", "httpx", "urllib", "urllib.request", "aiohttp"}
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        offending = imports & forbidden
        assert not offending, f"{path} imports forbidden HTTP client(s) {offending}"


def test_relevance_does_not_parse_headline_or_body() -> None:
    """No text parsing: ``compute_relevance``'s actual code never accesses
    ``.headline``/``.body`` as attribute names.

    Checked via bytecode-level attribute-name access (``co_names``), not
    source-text scanning, since the module's own docstring legitimately
    discusses "never references NewsItem.headline" in prose.
    """
    accessed_names = relevance.compute_relevance.__code__.co_names
    assert "headline" not in accessed_names
    assert "body" not in accessed_names
