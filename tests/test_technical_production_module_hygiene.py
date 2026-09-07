"""Stage 0B module-hygiene tests: ``app/technical/production.py`` must
depend only on the approved market-data/Technical/core seams - never on
Flow, Market Evaluation, Strategy Router, Judge, Policy/Decision, Risk,
Diversification, Statistics/Session, MT5, LLM, or any future API/Telegram
surface. Mirrors
``tests/test_flow_realtime_bootstrap_module_hygiene.py``'s own AST-based
approach one contour over.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.technical.production as production_module

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_PACKAGE_PREFIXES = (
    "app.flow",
    "app.market_evaluation",
    "app.strategies",
    "app.judge",
    "app.decision",
    "app.policy",
    "app.risk",
    "app.diversification",
    "app.statistics",
    "app.mt5",
    "app.llm",
    "app.api",
    "app.telegram",
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


def test_production_has_no_forbidden_imports() -> None:
    imports = _imports(inspect.getsource(production_module))
    for forbidden in _FORBIDDEN_PACKAGE_PREFIXES:
        offending = {name for name in imports if name == forbidden or name.startswith(forbidden + ".")}
        assert not offending, f"app.technical.production must not import {forbidden}: {offending}"


def test_production_never_mentions_forbidden_surfaces_textually() -> None:
    source = inspect.getsource(production_module).lower()
    for forbidden in ("telegram", "fastapi", "flask", "run_runtime_cycle", "openai", "metatrader5"):
        assert forbidden not in source


def test_production_module_importable_as_subprocess_without_optional_dependencies() -> None:
    """Does not require MetaTrader5/openai/fastapi/telegram to be installed
    just to import - mirrors Stage 0A's own "pure module, importable
    standalone" contract."""
    result = subprocess.run(
        [sys.executable, "-c", "import app.technical.production"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_module_only_imports_approved_top_level_packages() -> None:
    """Positive allowlist check, complementing the forbidden-prefix check
    above: every ``app.*`` import must be one of the approved seams."""
    approved_prefixes = (
        "app.core",
        "app.market_data",
        "app.technical",
        "app.technical_analysts",
        "app.technical_supervisor",
    )
    imports = _imports(inspect.getsource(production_module))
    for name in imports:
        if name == "app" or name.startswith("app."):
            assert any(name == prefix or name.startswith(prefix + ".") for prefix in approved_prefixes), (
                f"app.technical.production imports unapproved package: {name}"
            )
