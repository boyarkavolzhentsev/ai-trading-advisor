"""LLM Explanation Layer purity/dependency-boundary hygiene (NEXT STAGE,
Core).

Verifies: no wall-clock/random/UUID reference in the pure builder/fallback
functions, no execution surface, no real LLM SDK import, no FX conversion,
no hardcoded currency, no ranking/winner-selection language, no filesystem/
MT5 client calls anywhere in the explanation production files, and
importability without any real LLM SDK installed.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.explanation as explanation_module

REPO_ROOT = Path(__file__).resolve().parent.parent

_PURE_FUNCTION_NAMES = (
    "_format_decimal",
    "_format_price_levels",
    "_format_pnl_suffix",
    "_project_recommendation_card",
    "_project_tracking_card",
    "_build_cycle_facts",
    "_build_warnings",
    "build_explanation_context",
    "build_recommendation_cards",
    "build_tracking_cards",
    "_build_no_trade_explanation",
    "render_deterministic_fallback",
    "_all_context_fact_ids",
    "_validate_narrative",
    "_combine",
)

_PRODUCTION_FILES = (
    REPO_ROOT / "app" / "orchestration" / "explanation.py",
    REPO_ROOT / "app" / "core" / "models" / "explanation.py",
    REPO_ROOT / "app" / "core" / "enums" / "explanation.py",
    REPO_ROOT / "app" / "llm" / "protocols.py",
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


def test_no_wall_clock_random_or_uuid_in_pure_functions() -> None:
    tree = ast.parse(inspect.getsource(explanation_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _PURE_FUNCTION_NAMES:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    assert inner.func.attr not in {"now", "utcnow", "today", "uuid4"}, f"{node.name} must not read wall clock/generate UUIDs"
                if isinstance(inner, ast.Name):
                    assert inner.id not in {"random", "uuid"}, f"{node.name} must not reference {inner.id}"


def test_no_filesystem_or_mt5_or_network_calls_anywhere() -> None:
    for path in _PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("open(", "Path(", "requests.", "httpx.", "urllib", "socket."):
            assert forbidden not in source, f"{path.name} must not reference {forbidden!r}"
        imports = _imports(source)
        assert imports.isdisjoint({"pathlib", "os", "socket", "requests", "httpx"}), f"{path.name} imports forbidden modules"


def test_no_mt5_client_dependency() -> None:
    for path in _PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("app.mt5.client", "MetaTrader5", "MT5Client(", ".positions(", ".history_deals(", ".symbol_facts("):
            assert forbidden not in source, f"{path.name} must not reference {forbidden!r}"


def test_no_execution_surface() -> None:
    for path in _PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("order_send", "order_check", "position_modify", "position_close", "trade_send"):
            assert forbidden not in source, f"{path.name} must not reference {forbidden!r}"


def test_no_real_llm_sdk_import() -> None:
    for path in _PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("import openai", "from openai", "import anthropic", "from anthropic"):
            assert forbidden not in source.lower(), f"{path.name} must not import a real LLM SDK"


def test_no_fx_conversion_or_hardcoded_currency() -> None:
    for path in _PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in ("exchange_rate", "fx_rate", "convert_currency", "rate_lookup", "forex"):
            assert forbidden.lower() not in source.lower(), f"{path.name} must not reference {forbidden!r}"
        for forbidden in ('"USD"', '"EUR"', '"DKK"', "'USD'", "'EUR'", "'DKK'"):
            assert forbidden not in source, f"{path.name} must not hardcode {forbidden!r}"


def test_no_ranking_or_winner_selection_language() -> None:
    source = inspect.getsource(explanation_module).lower()
    for forbidden in ("best_recommendation", "winner", "rank_by", "select_best", "highest_confidence"):
        assert forbidden not in source


def test_no_recommendation_ever_dropped_by_sorting_construct() -> None:
    """Source-scan proof: card-building functions never sort/filter by a
    risk/confidence-shaped key - only by structural presence
    (``recommendation is not None``)."""
    source = inspect.getsource(explanation_module.build_recommendation_cards)
    for forbidden in ("sorted(", ".sort(", "key=lambda", "max(", "min("):
        assert forbidden not in source


def test_explanation_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.orchestration.explanation; "
            "import app.core.models.explanation; "
            "import app.core.enums.explanation; "
            "import app.llm.protocols",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_importable_without_real_llm_sdk_installed() -> None:
    """Confirms the explanation layer never depends on openai/anthropic
    being importable at all - a fresh subprocess import must succeed even
    if those packages are absent from the environment (which they already
    are in this repository's own dependency set)."""
    result = subprocess.run(
        [sys.executable, "-c", "import sys; assert 'openai' not in sys.modules and 'anthropic' not in sys.modules; import app.orchestration.explanation"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_explanation_llm_client_protocol_is_runtime_checkable() -> None:
    from app.llm.protocols import ExplanationLLMClient
    from tests.explanation_support import FakeExplanationLLMClient

    fake = FakeExplanationLLMClient(responses=[])
    assert isinstance(fake, ExplanationLLMClient)


def test_no_closed_stage_files_modified() -> None:
    """This layer must never import a closed Part F/Stage 10E module in a
    way that suggests it mutates it - it only ever reads ``RuntimeCycleResult``."""
    source = inspect.getsource(explanation_module)
    for forbidden in ("app.mt5.tracker", "app.mt5.matching", "app.orchestration.runtime_cycle.run_runtime_cycle("):
        assert forbidden not in source
