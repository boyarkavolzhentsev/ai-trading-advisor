"""Decision/Risk Pipeline purity/dependency-boundary hygiene.

Mirrors ``tests/test_orchestration_facts_module_hygiene.py``/``tests/test_
setup_construction_module_hygiene.py`` one architectural layer over:
``app.orchestration.decision_risk_pipeline`` may only orchestrate the
existing pure Stage 5-9 + Setup Construction components - it must never
import MT5/the filesystem/a new market-data provider/an execution surface,
must never call the wall clock, must never invoke Stage 10C broker sizing or
Stage 10E recommendation tracking, and must never mention order placement or
a presentation/API/LLM surface of any kind.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.decision_risk_pipeline as pipeline_module
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORT_PREFIXES = (
    "MetaTrader5",
    "app.mt5.client",
    "app.mt5.persistence",
    "app.mt5.recommendation_persistence",
    "app.mt5.risk",
    "app.mt5.history",
    "app.mt5.sizing",
    "app.mt5.matching",
    "app.mt5.tracker",
    "app.market_data",
    "app.execution",
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


def test_pipeline_module_imports_no_forbidden_dependency() -> None:
    source = inspect.getsource(pipeline_module)
    imports = _imports(source)
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.orchestration.decision_risk_pipeline must not import {offending}"


def test_pipeline_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(pipeline_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"


def test_pipeline_module_never_touches_filesystem() -> None:
    tree = ast.parse(inspect.getsource(pipeline_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"pathlib", "os", "json"})


def test_pipeline_module_never_mentions_order_placement_or_broker_sizing() -> None:
    source = inspect.getsource(pipeline_module)
    for forbidden in (
        "order_send",
        "order_check",
        "MT5Client(",
        "positions(",
        "history_deals(",
        "compute_broker_sizing",
        "create_tracked_recommendation",
    ):
        assert forbidden not in source


def test_pipeline_module_never_mentions_presentation_or_llm_surface() -> None:
    source = inspect.getsource(pipeline_module).lower()
    for forbidden in ("telegram", "anthropic", "openai", "fastapi", "flask", "llm"):
        assert forbidden not in source


def test_evaluate_decision_risk_pipeline_signature_takes_only_explicit_facts() -> None:
    signature = inspect.signature(evaluate_decision_risk_pipeline)
    assert set(signature.parameters) == {
        "flow",
        "technical",
        "external",
        "context",
        "evaluation_time",
        "symbol_facts",
        "m15_market_structure",
        "account_risk_snapshot_assembly",
        "trading_cycle_config",
        "locked_override",
    }


def test_pipeline_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.orchestration.decision_risk_pipeline; "
            "import app.core.models.decision_risk_pipeline; "
            "import app.core.enums.decision_risk_pipeline",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_9_production_package_imports_decision_risk_pipeline() -> None:
    """The pipeline sits above Stage 5-9: nothing in those packages, or in
    Runtime Fact Assembly, may depend on it - only a future runtime caller
    (not yet built) may invoke it."""
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
    for package in packages:
        package_dir = REPO_ROOT / package
        if not package_dir.exists():
            continue
        for path in package_dir.rglob("*.py"):
            imports = _imports(path.read_text(encoding="utf-8"))
            offending = {name for name in imports if name.startswith("app.orchestration.decision_risk_pipeline")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.orchestration.decision_risk_pipeline: {offending}"


def test_orchestration_facts_module_untouched_by_decision_risk_pipeline() -> None:
    """``app.orchestration.facts`` (Runtime Fact Assembly) must not import or
    call the decision/risk pipeline - the pipeline depends on its already-
    produced ``AccountRiskSnapshotAssembly`` output type only, never the
    other way around."""
    source = (REPO_ROOT / "app" / "orchestration" / "facts.py").read_text(encoding="utf-8")
    assert "decision_risk_pipeline" not in source
