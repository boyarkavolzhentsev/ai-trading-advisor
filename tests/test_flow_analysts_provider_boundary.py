"""Provider-agnosticism boundary tests for Stage 2B.

Stage 2B analyst code must never depend on Binance JSON, WebSocket stream
names, forceOrder/aggTrade payload shapes, REST response schemas, or any
``app.market_data`` provider implementation - normalization already
happened in Stage 1/2A.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.flow_analysts import base, funding, liquidation, open_interest, order_book, price_flow_relationship, protocols, taker_flow

MODULES = (base, protocols, taker_flow, liquidation, order_book, open_interest, funding, price_flow_relationship)

FORBIDDEN_SUBSTRINGS = (
    "binance",
    "forceorder",
    "aggtrade",
    "market_data.providers",
    "websocket",
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
def test_only_depends_on_core_and_flow_quality(module) -> None:
    _, imports = _source_and_imports(module)
    allowed_prefixes = ("app.core.", "app.flow_analysts.", "app.flow.quality", "app.flow.quality.")
    stdlib_or_third_party = {name for name in imports if not name.startswith("app.")}
    app_imports = imports - stdlib_or_third_party
    disallowed = {name for name in app_imports if not name.startswith(allowed_prefixes)}
    assert disallowed == set(), f"{module.__name__} imports outside the allowed app surface: {disallowed}"
