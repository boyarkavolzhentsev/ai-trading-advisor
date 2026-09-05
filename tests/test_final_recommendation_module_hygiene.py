"""Final Recommendation purity/dependency-boundary hygiene.

Mirrors ``tests/test_decision_risk_pipeline_module_hygiene.py`` one
architectural layer over: ``app.orchestration.final_recommendation`` may
only orchestrate the existing, unmodified Stage 10C ``compute_broker_sizing``
- it must never import MT5/the filesystem/a new market-data provider/an
execution surface, must never call the wall clock, must never invoke Stage
10E matching/tracking/persistence or construct a ``PositionRecord``, must
never reference ``MarketType``, and must never mention order placement or a
presentation/API/LLM surface of any kind.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.final_recommendation as final_recommendation_module
from app.core.models.final_recommendation import FinalRecommendation
from app.orchestration.final_recommendation import construct_final_recommendations

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORT_PREFIXES = (
    "MetaTrader5",
    "app.mt5.client",
    "app.mt5.persistence",
    "app.mt5.recommendation_persistence",
    "app.mt5.risk",
    "app.mt5.history",
    "app.mt5.matching",
    "app.mt5.tracker",
    "app.market_data",
    "app.execution",
    "app.core.enums.market",
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


def test_final_recommendation_module_imports_no_forbidden_dependency() -> None:
    source = inspect.getsource(final_recommendation_module)
    imports = _imports(source)
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.orchestration.final_recommendation must not import {offending}"


def test_final_recommendation_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(final_recommendation_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"


def test_final_recommendation_module_never_touches_filesystem() -> None:
    tree = ast.parse(inspect.getsource(final_recommendation_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"pathlib", "os", "json"})


def test_final_recommendation_module_never_mentions_order_or_execution() -> None:
    source = inspect.getsource(final_recommendation_module)
    for forbidden in (
        "order_send",
        "order_check",
        "MT5Client(",
        "account_info(",
        "symbol_info(",
        "positions(",
        "history_deals(",
        "create_tracked_recommendation",
        "MT5RecommendationPersistence(",
        "MT5TrackedRecommendation(",
        "PositionRecord(",
    ):
        assert forbidden not in source


def test_final_recommendation_module_never_mentions_market_type() -> None:
    source = inspect.getsource(final_recommendation_module)
    assert "MarketType" not in source
    assert "market" not in FinalRecommendation.model_fields


def test_final_recommendation_module_never_mentions_presentation_or_llm_surface() -> None:
    source = inspect.getsource(final_recommendation_module).lower()
    for forbidden in ("telegram", "anthropic", "openai", "fastapi", "flask", "llm"):
        assert forbidden not in source


def test_construct_final_recommendations_signature_takes_only_explicit_facts() -> None:
    signature = inspect.signature(construct_final_recommendations)
    assert set(signature.parameters) == {
        "decision_risk_pipeline_result",
        "symbol_facts",
        "account_currency",
        "trade_ids",
        "as_of",
    }


def test_final_recommendation_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.orchestration.final_recommendation; "
            "import app.core.models.final_recommendation; "
            "import app.core.enums.final_recommendation; "
            "import app.orchestration.errors",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_9_production_package_imports_final_recommendation() -> None:
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
            offending = {name for name in imports if name.startswith("app.orchestration.final_recommendation")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.orchestration.final_recommendation: {offending}"
