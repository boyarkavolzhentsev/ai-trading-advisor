"""Stage 0A module-hygiene tests: ``app/flow/realtime_bootstrap.py`` and
``app/flow/open_interest_poller.py`` must depend only on the approved
market-data/Flow/core seams - never on Market Evaluation, Strategy Router,
Judge, Policy/Decision, Risk, Diversification, Statistics/Session, MT5,
LLM, or any future API/Telegram surface. Mirrors
``tests/test_runtime_cycle_module_hygiene.py``'s own AST-based approach.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.flow.open_interest_poller as open_interest_poller_module
import app.flow.realtime_bootstrap as realtime_bootstrap_module

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_PACKAGE_PREFIXES = (
    "app.market_evaluation",
    "app.strategies",
    "app.judge",
    "app.decision",
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


def test_realtime_bootstrap_has_no_forbidden_imports() -> None:
    imports = _imports(inspect.getsource(realtime_bootstrap_module))
    for forbidden in _FORBIDDEN_PACKAGE_PREFIXES:
        offending = {name for name in imports if name == forbidden or name.startswith(forbidden + ".")}
        assert not offending, f"app.flow.realtime_bootstrap must not import {forbidden}: {offending}"


def test_open_interest_poller_has_no_forbidden_imports() -> None:
    imports = _imports(inspect.getsource(open_interest_poller_module))
    for forbidden in _FORBIDDEN_PACKAGE_PREFIXES:
        offending = {name for name in imports if name == forbidden or name.startswith(forbidden + ".")}
        assert not offending, f"app.flow.open_interest_poller must not import {forbidden}: {offending}"


def test_realtime_bootstrap_never_mentions_forbidden_surfaces_textually() -> None:
    source = inspect.getsource(realtime_bootstrap_module).lower()
    for forbidden in ("telegram", "fastapi", "flask", "run_runtime_cycle", "openai", "metatrader5"):
        assert forbidden not in source


def test_open_interest_poller_never_mentions_forbidden_surfaces_textually() -> None:
    source = inspect.getsource(open_interest_poller_module).lower()
    for forbidden in ("telegram", "fastapi", "flask", "run_runtime_cycle", "openai", "metatrader5"):
        assert forbidden not in source


def test_modules_importable_as_subprocess_without_optional_dependencies() -> None:
    """Neither module requires MetaTrader5/openai/fastapi/telegram to be
    installed just to import - mirrors run_runtime_cycle's own
    "pure module, importable standalone" contract."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.flow.open_interest_poller; import app.flow.realtime_bootstrap",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_10e_or_llm_package_imports_flow_realtime_bootstrap() -> None:
    packages = (
        "app/market_evaluation",
        "app/strategies",
        "app/judge",
        "app/decision",
        "app/risk",
        "app/diversification",
        "app/statistics",
        "app/mt5",
        "app/llm",
    )
    for package in packages:
        package_dir = REPO_ROOT / package
        if not package_dir.exists():
            continue
        for path in package_dir.rglob("*.py"):
            imports = _imports(path.read_text(encoding="utf-8"))
            offending = {
                name
                for name in imports
                if name.startswith("app.flow.realtime_bootstrap") or name.startswith("app.flow.open_interest_poller")
            }
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import Stage 0A Flow realtime modules: {offending}"
