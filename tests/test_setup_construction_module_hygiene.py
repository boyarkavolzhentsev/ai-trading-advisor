"""Setup Construction purity/dependency-boundary hygiene.

Mirrors ``tests/test_mt5_module_hygiene.py``/``tests/test_risk_gate_module_
hygiene.py`` one architectural layer over: ``app.decision.setup_construction``
must never import MT5, the filesystem, or a new market-data provider, must
never call the wall clock, must never invoke RiskGate/StatisticsAggregator,
and must never mention order placement.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.decision.setup_construction as setup_construction_module
from app.decision.setup_construction import SetupConstruction

REPO_ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORT_PREFIXES = (
    "MetaTrader5",
    "app.mt5",
    "app.market_data",
    "app.risk.engine",
    "app.risk.protocols",
    "app.statistics.aggregator",
    "app.statistics.protocols",
    "app.diversification",
    "app.mt5.sizing",
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


def test_setup_construction_module_imports_no_forbidden_dependency() -> None:
    source = inspect.getsource(setup_construction_module)
    imports = _imports(source)
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.decision.setup_construction must not import {offending}"


def test_setup_construction_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(setup_construction_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"


def test_setup_construction_module_never_touches_filesystem() -> None:
    tree = ast.parse(inspect.getsource(setup_construction_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"pathlib", "os", "json"})


def test_setup_construction_module_never_mentions_order_placement() -> None:
    source = inspect.getsource(setup_construction_module)
    for forbidden in ("order_send", "order_check"):
        assert forbidden not in source


def test_setup_construction_module_never_invokes_risk_gate_or_broker_sizing() -> None:
    """Substring-safe (mirrors ``tests/test_mt5_module_hygiene.py``'s own
    ``.aggregate(``/``.evaluate(`` check one layer over)."""
    source = inspect.getsource(setup_construction_module)
    for forbidden in (".evaluate(", "compute_broker_sizing", "MT5Client("):
        assert forbidden not in source


def test_setup_construction_never_calls_metatrader5_client_or_symbol_facts_itself() -> None:
    source = inspect.getsource(setup_construction_module)
    assert "symbol_facts(" not in source  # only ever received as a parameter, never called


def test_setup_construction_construct_signature_takes_only_explicit_facts() -> None:
    signature = inspect.signature(SetupConstruction.construct)
    assert set(signature.parameters) == {"self", "strategy_policy_result", "as_of", "symbol_facts", "m15_market_structure"}


def test_setup_construction_importable_as_pure_module_subprocess() -> None:
    """Mirrors ``tests/test_mt5_module_hygiene.py``'s own
    ``test_pure_mt5_modules_import_without_metatrader5_installed`` - Setup
    Construction never needs MT5 installed to import, since it never imports
    it."""
    result = subprocess.run(
        [sys.executable, "-c", "import app.decision.setup_construction; import app.core.models.setup_construction; import app.core.enums.setup_construction"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_10_production_package_imports_setup_construction() -> None:
    """Setup Construction is a new, additive leaf: nothing in Stage 5-10's
    own production packages may depend on it - only a future runtime
    orchestrator (not yet built) may call it."""
    packages = (
        "app/market_evaluation",
        "app/strategies",
        "app/judge",
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
            offending = {name for name in imports if name.startswith("app.decision.setup_construction")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.decision.setup_construction: {offending}"


def test_decision_gate_module_untouched_by_setup_construction() -> None:
    """``app.decision.gate`` (Stage 6C PolicyGate) must not import or mention
    Setup Construction at all - the two are siblings, not coupled."""
    source = (REPO_ROOT / "app" / "decision" / "gate.py").read_text(encoding="utf-8")
    assert "setup_construction" not in source
    assert "SetupConstruction" not in source
