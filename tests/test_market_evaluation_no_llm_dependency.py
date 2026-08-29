"""Stage 5A must never depend on an LLM client or perform network/HTTP I/O,
and must never use randomness or UUIDs (determinism guarantee)."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.market_evaluation import errors, evaluator, protocols

MODULES = (errors, evaluator, protocols)

FORBIDDEN_IMPORT_SUBSTRINGS = (
    "anthropic",
    "openai",
    "langchain",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "websocket",
    "random",
    "uuid",
)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_network_llm_random_or_uuid_import(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
        assert forbidden not in source, f"{module.__name__} references forbidden term {forbidden!r}"
