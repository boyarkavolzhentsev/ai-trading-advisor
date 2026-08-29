"""Stage 4G must never depend on an LLM client or perform network/HTTP I/O.

Mirrors ``tests/test_external_intelligence_no_llm_dependency.py`` one
contour over.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.external_intelligence_supervisor import errors, protocols, supervisor

MODULES = (errors, protocols, supervisor)

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
)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_network_or_llm_import(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
        assert forbidden not in source, f"{module.__name__} references forbidden term {forbidden!r}"
