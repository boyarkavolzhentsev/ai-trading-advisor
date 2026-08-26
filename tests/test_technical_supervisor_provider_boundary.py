"""Provider-agnosticism and analyst-implementation boundary tests for Stage 3C.

Stage 3C must never depend on Binance JSON, WebSocket stream names, provider
payload shapes, or any ``app.market_data`` implementation - and must never
import a *concrete* Stage 3B analyst implementation module (only the
provider-agnostic Stage 3A ``worse_of_many``/``DEFAULT_TECHNICAL_TIMEFRAMES``
primitives and Stage 3B's ``TechnicalAnalysisResult``/enum contracts are
allowed).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.technical_supervisor import errors, protocols, supervisor

MODULES = (errors, protocols, supervisor)

FORBIDDEN_SUBSTRINGS = (
    "binance",
    "forceorder",
    "aggtrade",
    "market_data.providers",
    "websocket",
)

FORBIDDEN_ANALYST_IMPLEMENTATION_MODULES = {
    "app.technical_analysts.trend",
    "app.technical_analysts.market_structure",
    "app.technical_analysts.volatility",
    "app.technical_analysts.momentum",
    "app.technical_analysts.moving_average",
    "app.technical_analysts.candle_structure",
    "app.technical_analysts.range_state",
}

ALLOWED_APP_IMPORT_PREFIXES = (
    "app.core.",
    "app.technical_supervisor.",
    "app.technical.quality",
    "app.technical.timeframes",
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


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_or_network_vocabulary(module) -> None:
    source, imports = _source_and_imports(module)
    lowered = source.lower()
    for forbidden in ("anthropic", "openai", "llm", "requests", "httpx", "aiohttp", "asyncio"):
        assert forbidden not in lowered, f"{module.__name__} references forbidden term {forbidden!r}"
