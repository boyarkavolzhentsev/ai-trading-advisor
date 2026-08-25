"""Stage 3A must consume only normalized ``OHLCVCandle``/``Timeframe``
contracts, never a concrete provider implementation or its vocabulary.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.technical import (
    alignment,
    candle_store,
    candle_structure,
    engine,
    errors,
    history,
    market_structure,
    momentum,
    moving_average,
    quality,
    range_state,
    timeframes,
    trend,
    volatility,
)

MODULES = (
    alignment, candle_store, candle_structure, engine, errors, history, market_structure,
    momentum, moving_average, quality, range_state, timeframes, trend, volatility,
)

FORBIDDEN_SUBSTRINGS = ("binance", "kline", "aggtrade", "forceorder", "websocket")


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
def test_no_provider_implementation_import(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {name for name in imports if name.startswith("app.market_data.providers")}
    assert offending == set(), f"{module.__name__} imports a concrete provider: {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_provider_vocabulary_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    lowered = source.lower()
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in lowered, f"{module.__name__} references forbidden provider term {forbidden!r}"
