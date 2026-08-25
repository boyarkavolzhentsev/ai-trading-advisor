"""Provider-agnosticism and analyst-implementation boundary tests for Stage 2C.

Stage 2C must never depend on Binance JSON, WebSocket stream names,
provider payload shapes, or any ``app.market_data`` implementation - and
must never import a *concrete* Stage 2B analyst implementation module
(only the shared, provider-agnostic ``app.flow_analysts.base`` primitives
and ``app.flow_analysts.protocols`` interface are allowed).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.flow_supervisor import errors, protocols, supervisor

MODULES = (errors, protocols, supervisor)

FORBIDDEN_SUBSTRINGS = (
    "binance",
    "forceorder",
    "aggtrade",
    "market_data.providers",
    "websocket",
)

FORBIDDEN_ANALYST_IMPLEMENTATION_MODULES = {
    "app.flow_analysts.taker_flow",
    "app.flow_analysts.liquidation",
    "app.flow_analysts.order_book",
    "app.flow_analysts.open_interest",
    "app.flow_analysts.funding",
    "app.flow_analysts.price_flow_relationship",
}

ALLOWED_APP_IMPORT_PREFIXES = (
    "app.core.",
    "app.flow_supervisor.",
    "app.flow_analysts.base",
    "app.flow_analysts.protocols",
)


def _source_and_imports(module) -> tuple[str, set[str]]:
    path = Path(inspect.getfile(module))
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return source, imports


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_market_data_provider_import(module) -> None:
    _, imports = _source_and_imports(module)
    assert not any(name.startswith("app.market_data") for name in imports)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_provider_vocabulary_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    lowered = source.lower()
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in lowered, f"{module.__name__} references forbidden term {forbidden!r}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_concrete_analyst_implementation_import(module) -> None:
    _, imports = _source_and_imports(module)
    assert imports.isdisjoint(FORBIDDEN_ANALYST_IMPLEMENTATION_MODULES)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_only_depends_on_allowed_app_surface(module) -> None:
    _, imports = _source_and_imports(module)
    app_imports = {name for name in imports if name.startswith("app.")}
    disallowed = {name for name in app_imports if not name.startswith(ALLOWED_APP_IMPORT_PREFIXES)}
    assert disallowed == set(), f"{module.__name__} imports outside the allowed app surface: {disallowed}"
