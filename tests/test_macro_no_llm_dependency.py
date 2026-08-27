"""Stage 4A must contain zero LLM dependency: no semantic classification,
summarization, hawkish/dovish detection, sentiment, relevance inference, or
structured extraction by a model.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models import economic_event
from app.macro import exceptions, history, protocols, provenance, quality

MODULES = (exceptions, history, protocols, provenance, quality, economic_event)

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
"""Deliberately excludes "sentiment": that is a legitimate future Stage 4D
domain *name* (cross-referenced from docstrings here), not by itself an LLM
indicator - a raw provider-supplied sentiment score is an ordinary fact, see
the Stage 4A design report's sentiment boundary section."""


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_SUBSTRINGS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden LLM-adjacent term(s): {offenders}"


def test_no_third_party_llm_import_anywhere_in_macro_package() -> None:
    import app.macro as macro_package

    package_dir = Path(inspect.getfile(macro_package)).parent
    for path in package_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        for term in ("openai", "anthropic", "langchain"):
            assert term not in source, f"{path} references forbidden LLM package {term!r}"
