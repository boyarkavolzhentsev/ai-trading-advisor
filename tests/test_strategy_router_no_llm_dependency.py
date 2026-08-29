"""Stage 6A ``app.strategies`` never imports an LLM SDK or a network client.

Mirrors ``tests/test_external_intelligence_supervisor_no_llm_dependency.py``
one layer over.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.strategies import protocols, router

MODULES = (router, protocols)

FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "httpx",
    "requests",
    "aiohttp",
    "websockets",
    "socket",
    "urllib",
)


def _imports(module) -> set[str]:
    path = Path(inspect.getfile(module))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_or_network_import(module) -> None:
    offending = {name for name in _imports(module) if name.startswith(FORBIDDEN_IMPORT_PREFIXES)}
    assert offending == set(), f"{module.__name__} imports forbidden LLM/network module(s): {offending}"
