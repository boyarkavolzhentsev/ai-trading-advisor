"""High-Impact Event Risk Gate module-hygiene tests (Corrective V1
Integration, test group AF).

Mirrors ``tests/test_setup_construction_module_hygiene.py``/``tests/
test_decision_risk_pipeline_module_hygiene.py``'s own AST-based approach:
``app.decision.high_impact_event_gate`` must never touch MT5, the
filesystem, the network, the wall clock, an LLM surface, Flow/Technical
evidence, ``app.macro``/External Intelligence, or order placement/broker
sizing - and must never modify ``app.decision.setup_construction``.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.decision.high_impact_event_gate as gate_module

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORT_PREFIXES = (
    "MetaTrader5",
    "app.mt5",
    "app.market_data",
    "app.execution",
    "app.macro",
    "app.external_intelligence_analysts",
    "app.external_intelligence_supervisor",
    "app.flow",
    "app.technical",
    "app.judge",
    "app.market_evaluation",
    "app.risk",
    "app.diversification",
    "app.statistics",
)


def _imports(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_gate_module_imports_no_forbidden_dependency() -> None:
    imports = _imports(inspect.getsource(gate_module))
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.decision.high_impact_event_gate must not import {offending}"


def test_gate_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(gate_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}


def test_gate_module_never_touches_filesystem_or_network() -> None:
    imports = _imports(inspect.getsource(gate_module))
    assert imports.isdisjoint({"pathlib", "os", "json", "httpx", "requests", "socket"})


def test_gate_module_never_mentions_order_execution_or_llm_surfaces() -> None:
    source = inspect.getsource(gate_module).lower()
    for forbidden in (
        "order_send",
        "order_check",
        "mt5client(",
        "telegram",
        "anthropic",
        "openai",
        "fastapi",
        "flask",
    ):
        assert forbidden not in source


def test_gate_module_does_not_modify_setup_construction() -> None:
    """The gate composes ``to_candidate_risk_inputs`` via import only -
    never redefines, monkeypatches, or reimplements it."""
    source = inspect.getsource(gate_module)
    assert "def to_candidate_risk_inputs" not in source
    assert "setup_construction.to_candidate_risk_inputs =" not in source
    tree = ast.parse(source)
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.decision.setup_construction"
        for alias in node.names
    }
    assert "to_candidate_risk_inputs" in imported_names


def test_setup_construction_file_has_no_high_impact_event_reference() -> None:
    """Mechanical proof that ``app/decision/setup_construction.py`` was
    never touched to support this feature."""
    source = (REPO_ROOT / "app" / "decision" / "setup_construction.py").read_text(encoding="utf-8")
    assert "high_impact_event" not in source.lower()


def test_gate_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import app.decision.high_impact_event_gate; import app.core.models.high_impact_event; import app.core.enums.high_impact_event"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


# --- bridge adapter (file-reader) hygiene ---

import app.high_impact_event_bridge.file_reader as file_reader_module  # noqa: E402


def test_file_reader_module_imports_no_mt5_or_macro_dependency() -> None:
    imports = _imports(inspect.getsource(file_reader_module))
    offending = {name for name in imports if name.startswith(("MetaTrader5", "app.mt5", "app.macro"))}
    assert not offending, f"app.high_impact_event_bridge.file_reader must not import {offending}"


def test_file_reader_module_never_writes_a_file() -> None:
    source = inspect.getsource(file_reader_module)
    for forbidden in ("write_text(", "write_bytes(", ".write(", "open(", "os.remove", "unlink("):
        assert forbidden not in source


def test_file_reader_module_never_constructs_economic_event() -> None:
    source = inspect.getsource(file_reader_module)
    assert "EconomicEvent" not in source
