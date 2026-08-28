"""Stage 4C must remain an independent contour: no import edge into
``app.flow``/``app.flow_analysts``/``app.flow_supervisor`` from anywhere
under ``app.news``, and no reference to any of their model names.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

from app.news import exceptions, history, protocols, provenance

MODULES = (exceptions, history, protocols, provenance)

FORBIDDEN_MODULE_PREFIXES = ("app.flow.", "app.flow_analysts", "app.flow_supervisor")
FORBIDDEN_EXACT_MODULES = {"app.flow"}
FORBIDDEN_NAMES = (
    "FlowFeatureSnapshot",
    "FlowAnalysisResult",
    "FlowSupervisorResult",
    "FlowAnalyst",
    "FlowSupervisor",
)

MODEL_MODULE_NAMES = ("news_item",)


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
def test_no_flow_module_imported(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {
        name for name in imports if name in FORBIDDEN_EXACT_MODULES or name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }
    assert offending == set(), f"{module.__name__} imports forbidden flow module(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_flow_model_name_referenced_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in source, f"{module.__name__} references forbidden flow name {forbidden!r}"


@pytest.mark.parametrize("model_module_name", MODEL_MODULE_NAMES)
def test_news_item_model_has_no_flow_coupling(model_module_name: str) -> None:
    module = importlib.import_module(f"app.core.models.{model_module_name}")
    source, imports = _source_and_imports(module)
    offending = {
        name for name in imports if name in FORBIDDEN_EXACT_MODULES or name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }
    assert offending == set()
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in source
