"""Stage 6B Judge must never parse ``MarketEvaluationContext.symbol`` or
otherwise infer FX base/quote role - the currency-role gap is a documented
design blocker, not something to work around implicitly."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.judge import judge, protocols

MODULES = (judge, protocols)

_STRING_METHODS = {
    "startswith",
    "endswith",
    "split",
    "rsplit",
    "partition",
    "rpartition",
    "find",
    "index",
    "replace",
    "strip",
    "lstrip",
    "rstrip",
    "removeprefix",
    "removesuffix",
}


def test_no_string_method_called_on_symbol_attribute() -> None:
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in _STRING_METHODS:
                continue
            target = node.func.value
            if isinstance(target, ast.Attribute) and target.attr == "symbol":
                raise AssertionError(f"{module.__name__} calls .{node.func.attr}() on a .symbol attribute")


def test_context_symbol_never_referenced() -> None:
    """Judge never even reads ``context.symbol`` - it consumes only already-
    aligned/structural facts, never the raw scope identity."""
    for module in (judge,):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert "context.symbol" not in source
        assert ".context." not in source
