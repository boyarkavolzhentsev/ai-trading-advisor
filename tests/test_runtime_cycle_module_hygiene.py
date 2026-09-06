"""Runtime Cycle Orchestration purity/dependency-boundary hygiene (Final
Runtime Integration, Part F).

``app.orchestration.runtime_cycle`` is the first intentionally impure
runtime-cycle boundary - it IS allowed to import ``app.mt5.*`` (unlike
``app.orchestration.final_recommendation``/``app.orchestration.
tracking_integration``, which forbid it). This module instead verifies the
narrower set of invariants that remain true of an orchestration layer that
must never itself reimplement business logic or place an order: no direct
``MetaTrader5`` import, no order-placement/execution surface, no
presentation/LLM surface, no wall-clock/random/UUID reference inside its pure
helpers, and importability without the real ``MetaTrader5`` package
installed.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.runtime_cycle as runtime_cycle_module
from app.orchestration.runtime_cycle import run_runtime_cycle

REPO_ROOT = Path(__file__).resolve().parent.parent

_PURE_HELPER_NAMES = (
    "_symbol_has_unresolved_tracking",
    "_evaluate_netting_guard",
    "_compute_history_start",
    "_advance_all_existing_tracking",
    "_compute_cycle_outcome",
)


def test_module_never_imports_metatrader5_directly() -> None:
    source = inspect.getsource(runtime_cycle_module)
    assert "import MetaTrader5" not in source
    assert "MetaTrader5" not in source


def test_module_never_mentions_order_placement_or_execution() -> None:
    source = inspect.getsource(runtime_cycle_module)
    for forbidden in (
        "order_send",
        "order_check",
        "position_modify",
        "position_close",
        "trade_send",
    ):
        assert forbidden not in source


def test_module_never_mentions_presentation_or_llm_surface() -> None:
    source = inspect.getsource(runtime_cycle_module).lower()
    for forbidden in ("telegram", "anthropic", "openai", "fastapi", "flask", "llm"):
        assert forbidden not in source


def test_pure_helpers_never_call_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(runtime_cycle_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _PURE_HELPER_NAMES:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    assert inner.func.attr not in {"now", "utcnow", "today", "uuid4"}, (
                        f"{node.name} must not read the wall clock or generate UUIDs"
                    )
                if isinstance(inner, ast.Name):
                    assert inner.id not in {"random", "uuid"}, f"{node.name} must not reference {inner.id}"


def test_pure_helpers_never_touch_filesystem_or_mt5_client() -> None:
    tree = ast.parse(inspect.getsource(runtime_cycle_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _PURE_HELPER_NAMES:
            source_segment = ast.get_source_segment(inspect.getsource(runtime_cycle_module), node) or ""
            for forbidden in ("open(", ".read(", ".write(", "client.", "Path("):
                assert forbidden not in source_segment, f"{node.name} must stay pure: found {forbidden!r}"


def test_run_runtime_cycle_signature_has_no_default_wall_clock_as_of() -> None:
    signature = inspect.signature(run_runtime_cycle)
    assert "as_of" in signature.parameters
    assert signature.parameters["as_of"].default is inspect.Parameter.empty


def test_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.orchestration.runtime_cycle; "
            "import app.core.models.runtime_cycle; "
            "import app.core.enums.runtime_cycle",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_10e_production_package_imports_runtime_cycle() -> None:
    packages = (
        "app/market_evaluation",
        "app/strategies",
        "app/judge",
        "app/decision",
        "app/risk",
        "app/diversification",
        "app/statistics",
        "app/mt5",
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

    for package in packages:
        package_dir = REPO_ROOT / package
        if not package_dir.exists():
            continue
        for path in package_dir.rglob("*.py"):
            imports = _imports(path.read_text(encoding="utf-8"))
            offending = {name for name in imports if name.startswith("app.orchestration.runtime_cycle")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.orchestration.runtime_cycle: {offending}"
