"""Stage 3B must remain independent of the flow contour.

Mirrors ``tests/test_technical_no_flow_coupling.py`` one layer over: no
import edge into ``app.flow``/``app.flow_analysts``/``app.flow_supervisor``
from anywhere under ``app.technical_analysts``, and no reference to any of
their models.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.technical_analysts import base, candle_structure, market_structure, momentum, moving_average, protocols, range_state, trend, volatility

MODULES = (base, protocols, trend, market_structure, volatility, momentum, moving_average, candle_structure, range_state)

FORBIDDEN_MODULE_PREFIXES = ("app.flow.", "app.flow_analysts", "app.flow_supervisor")
FORBIDDEN_EXACT_MODULES = {"app.flow"}
FORBIDDEN_NAMES = (
    "FlowFeatureSnapshot",
    "FlowAnalysisResult",
    "FlowSupervisorResult",
    "FlowAnalyst",
    "FlowSupervisor",
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
def test_no_flow_module_imported(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {
        name
        for name in imports
        if name in FORBIDDEN_EXACT_MODULES or name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }
    assert offending == set(), f"{module.__name__} imports forbidden flow module(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_flow_model_name_referenced_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in source, f"{module.__name__} references forbidden flow name {forbidden!r}"


def test_technical_analysis_result_model_has_no_flow_import() -> None:
    import app.core.models.technical_analysis_result as result_module
    import app.core.models.technical_evidence as evidence_module

    for module in (result_module, evidence_module):
        _, imports = _source_and_imports(module)
        offending = {name for name in imports if name.startswith(FORBIDDEN_MODULE_PREFIXES) or name in FORBIDDEN_EXACT_MODULES}
        assert offending == set()


def test_technical_analysis_enums_have_no_flow_import() -> None:
    import app.core.enums.technical_analysis as enums_module

    _, imports = _source_and_imports(enums_module)
    offending = {name for name in imports if name.startswith(FORBIDDEN_MODULE_PREFIXES) or name in FORBIDDEN_EXACT_MODULES}
    assert offending == set()
