"""Stage 4E must contain zero LLM dependency: no semantic classification,
summarization, interpretation of on-chain facts, or structured extraction by
a model.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models import (
    exchange_flow_observation,
    network_activity_observation,
    stablecoin_supply_observation,
    supply_observation,
)
from app.onchain import exceptions, history, protocols, provenance

MODULES = (
    exceptions,
    history,
    protocols,
    provenance,
    network_activity_observation,
    supply_observation,
    exchange_flow_observation,
    stablecoin_supply_observation,
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


def test_no_third_party_llm_import_anywhere_in_onchain_package() -> None:
    import app.onchain as onchain_package

    package_dir = Path(inspect.getfile(onchain_package)).parent
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for term in ("openai", "anthropic", "langchain"):
            assert term not in source, f"{path} references forbidden LLM package {term!r}"


def test_no_http_client_import_anywhere_in_onchain_package() -> None:
    """No real provider adapter/HTTP integration exists in Stage 4E."""
    import ast

    import app.onchain as onchain_package

    package_dir = Path(inspect.getfile(onchain_package)).parent
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
