"""Tracking Integration purity/dependency-boundary hygiene (Final Runtime
Integration, Part E).

Mirrors ``tests/test_final_recommendation_module_hygiene.py`` one seam over:
``app.orchestration.tracking_integration`` may only orchestrate the existing,
unmodified Stage 10E ``create_tracked_recommendation`` - it must never import
MT5/the filesystem/either persistence module/a new market-data provider/an
execution surface, must never call the wall clock, must never invoke
matching/lifecycle-reconstruction/persistence, and must never mention order
placement or a presentation/API/LLM surface of any kind.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.tracking_integration as tracking_integration_module
from app.orchestration.tracking_integration import construct_tracked_recommendations

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORT_PREFIXES = (
    "MetaTrader5",
    "app.mt5.client",
    "app.mt5.persistence",
    "app.mt5.recommendation_persistence",
    "app.mt5.recommendation_provenance_persistence",
    "app.mt5.matching",
    "app.mt5.history",
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


def test_tracking_integration_module_imports_no_forbidden_dependency() -> None:
    source = inspect.getsource(tracking_integration_module)
    imports = _imports(source)
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.orchestration.tracking_integration must not import {offending}"


def test_tracking_integration_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(tracking_integration_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"


def test_tracking_integration_module_never_touches_filesystem() -> None:
    tree = ast.parse(inspect.getsource(tracking_integration_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"pathlib", "os", "json"})


def test_tracking_integration_module_never_mentions_forbidden_operations() -> None:
    source = inspect.getsource(tracking_integration_module)
    for forbidden in (
        "order_send",
        "order_check",
        "MT5Client(",
        "account_info(",
        "symbol_info(",
        "history_deals(",
        "match_recommendation",
        "advance_tracked_recommendation",
        "reconstruct_position_lifecycle",
        "MT5RecommendationPersistence(",
        "MT5RecommendationProvenancePersistence(",
    ):
        assert forbidden not in source


def test_tracking_integration_module_never_mentions_presentation_or_llm_surface() -> None:
    source = inspect.getsource(tracking_integration_module).lower()
    for forbidden in ("telegram", "anthropic", "openai", "fastapi", "flask", "llm"):
        assert forbidden not in source


def test_construct_tracked_recommendations_signature_takes_only_explicit_facts() -> None:
    signature = inspect.signature(construct_tracked_recommendations)
    assert set(signature.parameters) == {
        "final_recommendation_construction_result",
        "as_of",
        "market",
        "pre_existing_positions_read_status",
        "pre_existing_positions",
    }


def test_tracking_integration_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.orchestration.tracking_integration; "
            "import app.core.models.tracking_integration; "
            "import app.core.models.final_recommendation_provenance",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_10e_production_package_imports_tracking_integration() -> None:
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
            offending = {name for name in imports if name.startswith("app.orchestration.tracking_integration")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.orchestration.tracking_integration: {offending}"
