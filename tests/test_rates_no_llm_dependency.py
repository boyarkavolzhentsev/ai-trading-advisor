"""Stage 4B must contain zero LLM dependency: no semantic classification,
summarization, hawkish/dovish detection, sentiment, relevance inference, or
structured extraction by a model.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models import government_yield_observation, policy_rate_observation, tenor
from app.rates import exceptions, history, protocols, provenance

MODULES = (
    exceptions,
    history,
    protocols,
    provenance,
    policy_rate_observation,
    government_yield_observation,
    tenor,
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
    "hawkish",
    "dovish",
)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_SUBSTRINGS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden LLM-adjacent term(s): {offenders}"


def test_no_third_party_llm_import_anywhere_in_rates_package() -> None:
    import app.rates as rates_package

    package_dir = Path(inspect.getfile(rates_package)).parent
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for term in ("openai", "anthropic", "langchain"):
            assert term not in source, f"{path} references forbidden LLM package {term!r}"


def test_no_http_client_import_anywhere_in_rates_package() -> None:
    """No real provider adapter/HTTP integration exists in Stage 4B."""
    import ast

    import app.rates as rates_package

    package_dir = Path(inspect.getfile(rates_package)).parent
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
