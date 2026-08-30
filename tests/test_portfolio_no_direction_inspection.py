"""Stage 8 must never inspect direction: no ``.direction`` attribute access,
no ``DirectionalCandidate`` import/reference, no LONG/SHORT/BUY/SELL
vocabulary anywhere in ``app.diversification``."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.diversification import protocols, supervisor

MODULES = (supervisor, protocols)


def test_no_direction_attribute_access() -> None:
    for module in MODULES:
        path = Path(inspect.getfile(module))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "direction":
                raise AssertionError(f"{module.__name__} accesses a '.direction' attribute")


def test_no_directional_candidate_import_or_reference() -> None:
    for module in MODULES:
        path = Path(inspect.getfile(module))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names.update(alias.name for alias in node.names)
        assert "DirectionalCandidate" not in imported_names, f"{module.__name__} imports DirectionalCandidate"

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in {"DirectionalCandidate", "LONG", "SHORT", "BUY", "SELL"}:
                raise AssertionError(f"{module.__name__} references forbidden directional identifier {node.id!r}")
