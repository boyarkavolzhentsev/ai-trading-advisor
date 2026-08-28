"""Stage 4F must contain zero LLM dependency and zero network dependency."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.external_intelligence_analysts import base, config, macro_event, news_sentiment, on_chain, protocols, rates_yield

MODULES = (base, config, protocols, macro_event, rates_yield, news_sentiment, on_chain)

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


def test_no_third_party_llm_import_anywhere_in_package() -> None:
    import app.external_intelligence_analysts as package

    package_dir = Path(inspect.getfile(package)).parent
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for term in ("openai", "anthropic", "langchain"):
            assert term not in source, f"{path} references forbidden LLM package {term!r}"


def test_no_http_client_or_network_import_anywhere_in_package() -> None:
    import ast

    import app.external_intelligence_analysts as package

    package_dir = Path(inspect.getfile(package)).parent
    forbidden = {"requests", "httpx", "urllib", "urllib.request", "aiohttp", "socket"}
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
        assert not offending, f"{path} imports forbidden network dependency {offending}"


def test_news_sentiment_analyzer_does_not_read_headline_or_body() -> None:
    """No headline/body text is ever parsed - checked at the bytecode level
    (attribute-name access), not source-text scanning, since the module's
    own docstring legitimately explains this absence in prose."""
    accessed_names = news_sentiment.NewsSentimentAnalyst.analyze.__code__.co_names
    assert "headline" not in accessed_names
    assert "body" not in accessed_names
