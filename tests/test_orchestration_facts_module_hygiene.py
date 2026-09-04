"""Runtime Fact Assembly purity/dependency-boundary hygiene.

Mirrors ``tests/test_setup_construction_module_hygiene.py``/``tests/test_mt5_
module_hygiene.py`` one architectural layer over: ``app.orchestration.facts``
must never import MT5/the filesystem/a new market-data provider, must never
call the wall clock, must never invoke RiskGate/PortfolioSupervisor/
SessionGate/SetupConstruction/StatisticsAggregator, and must never mention
order placement, an LLM dependency, or an API/Telegram surface - this step
is Runtime Fact Assembly only.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.orchestration.facts as facts_module
from app.orchestration.facts import assemble_account_risk_snapshot

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
    "app.risk.engine",
    "app.risk.protocols",
    "app.diversification",
    "app.statistics.aggregator",
    "app.statistics.protocols",
    "app.decision.setup_construction",
    "app.decision.gate",
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


def test_facts_module_imports_no_forbidden_dependency() -> None:
    source = inspect.getsource(facts_module)
    imports = _imports(source)
    offending = {name for name in imports if name.startswith(_FORBIDDEN_IMPORT_PREFIXES)}
    assert not offending, f"app.orchestration.facts must not import {offending}"


def test_facts_module_never_calls_wall_clock_random_or_uuid() -> None:
    tree = ast.parse(inspect.getsource(facts_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"


def test_facts_module_never_touches_filesystem() -> None:
    tree = ast.parse(inspect.getsource(facts_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"pathlib", "os", "json"})


def test_facts_module_never_mentions_order_placement_or_execution() -> None:
    source = inspect.getsource(facts_module)
    for forbidden in ("order_send", "order_check", "MT5Client(", "positions(", "history_deals(", "symbol_facts("):
        assert forbidden not in source


def test_facts_module_never_invokes_downstream_stages() -> None:
    """Substring-safe, mirroring the identical existing-precedent checks in
    ``tests/test_mt5_module_hygiene.py``/``tests/test_setup_construction_
    module_hygiene.py``: no ``.evaluate(``/``.apply(``/``.route(``/
    ``.judge(``/``.aggregate(``/``.construct(`` call site anywhere in this
    module - it only assembles already-produced facts."""
    source = inspect.getsource(facts_module)
    for forbidden in (".evaluate(", ".apply(", ".route(", ".judge(", ".aggregate(", ".construct(", "compute_broker_sizing", "create_tracked_recommendation"):
        assert forbidden not in source


def test_facts_module_never_mentions_llm_api_or_telegram() -> None:
    source = inspect.getsource(facts_module).lower()
    for forbidden in ("telegram", "anthropic", "openai", "fastapi", "flask", "llm"):
        assert forbidden not in source


def test_assemble_account_risk_snapshot_signature_takes_only_explicit_facts() -> None:
    signature = inspect.signature(assemble_account_risk_snapshot)
    assert set(signature.parameters) == {"as_of", "rollover_snapshot", "realized_daily_pnl_assessment", "open_risk_assessment"}


def test_facts_module_importable_as_pure_module_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import app.orchestration.facts; import app.core.models.runtime_fact_assembly; import app.core.enums.runtime_fact_assembly"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_stage_5_to_10_production_package_imports_orchestration_facts() -> None:
    """Runtime Fact Assembly is a new, additive leaf: nothing in Stage 5-10's
    own production packages may depend on it - only a future runtime
    orchestrator (not yet built) may call it."""
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
            offending = {name for name in imports if name.startswith("app.orchestration")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.orchestration: {offending}"


def test_orchestration_package_still_has_no_cycle_setup_tracking_or_feedback_module() -> None:
    """This step is Runtime Fact Assembly only - cycle.py/setup.py/
    tracking.py/feedback.py orchestration remain unimplemented."""
    package_dir = REPO_ROOT / "app" / "orchestration"
    forbidden_names = {"cycle.py", "setup.py", "tracking.py", "feedback.py", "execution.py", "api.py", "telegram.py", "llm.py"}
    present = {p.name for p in package_dir.glob("*.py")}
    assert present.isdisjoint(forbidden_names)


def test_orchestration_init_still_unimplemented_stub() -> None:
    """Mirrors the established repository convention (``app/decision/
    __init__.py``, ``app/risk/__init__.py`` etc. all stay docstring-only
    stubs even once real modules exist in the same package) - real modules
    are always imported by their full path, never re-exported at the
    package __init__ level."""
    source = (REPO_ROOT / "app" / "orchestration" / "__init__.py").read_text(encoding="utf-8")
    assert "import" not in source
