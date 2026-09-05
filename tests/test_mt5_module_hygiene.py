"""Stage 10A/10B/10C/10D/10E dependency-boundary hygiene.

Only ``app.mt5.client`` may import ``MetaTrader5``; nothing in ``app.core``
or Stage 5-9 production packages may import ``app.mt5``, and no ``app.mt5``
module may import a Stage 5-9 production package's own logic (only the
narrow, explicitly-approved ``PositionRecord`` exception for
``app.mt5.tracker``); the protocol exposes no order-placement surface and no
order-history surface; and ``app/mt5`` contains exactly its approved Stage
10A + 10B + 10C + 10D + 10E file set (rollover transition/persistence,
open-risk assessment, broker sizing, deal-history realized-PnL assessment,
recommendation<->broker matching, position-lifecycle tracking, tracking-state
persistence)."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.mt5.client
import app.mt5.errors
import app.mt5.history
import app.mt5.matching
import app.mt5.protocols
import app.mt5.recommendation_persistence
import app.mt5.tracker
from app.mt5.client import MT5Client
from app.mt5.protocols import MT5ClientProtocol

REPO_ROOT = Path(__file__).resolve().parent.parent

_STAGE_5_9_PACKAGES = (
    "app/market_evaluation",
    "app/strategies",
    "app/judge",
    "app/decision",
    "app/risk",
    "app/money_management",
    "app/diversification",
    "app/statistics",
)

_PURE_STAGE_10E_MODULES = (app.mt5.matching, app.mt5.tracker)
"""``app.mt5.matching``/``app.mt5.tracker`` - the only two new Stage 10E
modules required to stay pure (no filesystem, no wall clock, no random/UUID,
no MetaTrader5). ``app.mt5.recommendation_persistence`` is deliberately
excluded: it is Stage 10E's one impure, filesystem-owning module."""


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_client_module_imports_metatrader5() -> None:
    mt5_package_dir = REPO_ROOT / "app" / "mt5"
    for path in mt5_package_dir.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name == "MetaTrader5" or name.startswith("MetaTrader5.")}
        if path.name == "client.py":
            continue  # client.py imports it lazily inside a function body, not at module level - checked separately
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import MetaTrader5: {offending}"


def test_client_module_has_no_top_level_metatrader5_import() -> None:
    """``MetaTrader5`` must be importable lazily only (inside a function
    body), never at module scope, so ``import app.mt5.client`` never
    requires the package installed."""
    tree = ast.parse((REPO_ROOT / "app" / "mt5" / "client.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert not any(alias.name.startswith("MetaTrader5") for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("MetaTrader5")


def test_pure_mt5_modules_import_without_metatrader5_installed() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.mt5.protocols; import app.mt5.errors; import app.mt5.rollover; import app.mt5.persistence; "
            "import app.mt5.risk; import app.mt5.sizing; import app.mt5.history; "
            "import app.mt5.matching; import app.mt5.tracker; import app.mt5.recommendation_persistence; "
            "import app.core.models.mt5_runtime; import app.core.enums.mt5_runtime; "
            "import app.core.models.mt5_rollover; import app.core.enums.mt5_rollover; import app.core.config.mt5_rollover; "
            "import app.core.models.mt5_position; import app.core.enums.mt5_position; "
            "import app.core.models.mt5_symbol; import app.core.enums.mt5_symbol; "
            "import app.core.models.mt5_sizing; import app.core.enums.mt5_sizing; "
            "import app.core.models.mt5_history; import app.core.enums.mt5_history; "
            "import app.core.models.mt5_matching; import app.core.enums.mt5_matching; "
            "import app.core.models.mt5_tracking",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_no_core_package_imports_app_mt5() -> None:
    for path in (REPO_ROOT / "app" / "core").rglob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name == "app.mt5" or name.startswith("app.mt5.")}
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.mt5: {offending}"


def test_no_stage_5_to_9_production_package_imports_app_mt5() -> None:
    for package in _STAGE_5_9_PACKAGES:
        package_dir = REPO_ROOT / package
        if not package_dir.exists():
            continue
        for path in package_dir.rglob("*.py"):
            imports = _imports(path)
            offending = {name for name in imports if name == "app.mt5" or name.startswith("app.mt5.")}
            assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.mt5: {offending}"


def test_protocol_exposes_no_order_placement_or_order_history_methods() -> None:
    """``history_deals`` is now approved (Stage 10D); ``history_orders``
    remains forbidden - Stage 10D's deals alone already carry sufficient
    ``order``/``position_id`` linkage for a future Stage 10E, so no order-
    history method was ever needed."""
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    forbidden = {"order_send", "order_check", "open_positions", "symbol_specification", "history_orders"}
    assert members.isdisjoint(forbidden)


def test_protocol_exposes_exactly_the_approved_stage_10a_10b_10c_10d_methods() -> None:
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    assert members == {"initialize", "runtime_status", "account_facts", "positions", "symbol_facts", "history_deals", "shutdown"}


def test_client_source_never_mentions_order_send_or_order_check() -> None:
    source = inspect.getsource(app.mt5.client)
    assert "order_send" not in source
    assert "order_check" not in source


def test_protocol_and_errors_source_never_mention_order_send_or_order_check() -> None:
    for module in (app.mt5.protocols, app.mt5.errors):
        source = inspect.getsource(module)
        assert "order_send" not in source
        assert "order_check" not in source


def test_client_satisfies_protocol_structurally() -> None:
    from tests.mt5_support import FakeRawMT5Module

    client = MT5Client(mt5_module=FakeRawMT5Module())
    assert isinstance(client, MT5ClientProtocol)


def test_protocol_is_runtime_checkable() -> None:
    assert getattr(MT5ClientProtocol, "_is_runtime_protocol", False) is True


def test_fake_client_satisfies_protocol() -> None:
    from tests.mt5_support import FakeMT5Client

    assert isinstance(FakeMT5Client(), MT5ClientProtocol)


def test_app_mt5_contains_only_approved_stage_10a_10b_10c_10d_10e_files() -> None:
    package_dir = REPO_ROOT / "app" / "mt5"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == [
        "__init__.py",
        "client.py",
        "errors.py",
        "history.py",
        "matching.py",
        "persistence.py",
        "protocols.py",
        "recommendation_persistence.py",
        "risk.py",
        "rollover.py",
        "sizing.py",
        "tracker.py",
    ]


def test_no_forbidden_names_present() -> None:
    """``matching.py``/``tracker.py`` are now approved (Stage 10E) and
    removed from this denylist. ``models.py``/``enums.py``/
    ``normalization.py`` remain forbidden permanently - domain models/enums
    live under ``app/core``, never under ``app/mt5`` (see Stage 10A-10E
    precedent)."""
    package_dir = REPO_ROOT / "app" / "mt5"
    forbidden_names = {"models.py", "enums.py", "normalization.py"}
    present = {p.name for p in package_dir.glob("*.py")}
    assert present.isdisjoint(forbidden_names)


def test_only_tracker_module_imports_position_record() -> None:
    """``app.mt5.tracker`` is Stage 10E's one approved exception: it is the
    module responsible for creating/updating ``PositionRecord`` from broker
    evidence. No other ``app/mt5`` module (including ``app.mt5.matching``,
    which only ever produces an ``MT5MatchResult``) may import it."""
    mt5_package_dir = REPO_ROOT / "app" / "mt5"
    for path in mt5_package_dir.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name == "app.core.models.position"}
        if path.name == "tracker.py":
            assert offending, "tracker.py is expected to import app.core.models.position"
            continue
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.core.models.position: {offending}"


def test_no_app_mt5_module_imports_account_risk_snapshot_or_risk_gate() -> None:
    """Stage 10D/10E both remain fact producers only: no ``app/mt5`` module
    may import ``AccountRiskSnapshot``/``RiskGate`` (Stage 7's own
    contracts) or ``StatisticsAggregator`` (Stage 9's own contract) -
    constructing/invoking any of them is explicitly out of Stage 10D/10E
    scope; final runtime integration (not yet built) owns that assembly."""
    mt5_package_dir = REPO_ROOT / "app" / "mt5"
    for path in mt5_package_dir.glob("*.py"):
        imports = _imports(path)
        offending = {
            name
            for name in imports
            if name
            in {
                "app.core.models.risk_gate_result",
                "app.risk.engine",
                "app.risk.protocols",
                "app.statistics.aggregator",
                "app.statistics.protocols",
            }
        }
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import {offending}"


def test_no_app_mt5_module_imports_stage_5_to_9_production_packages() -> None:
    """The reverse direction of ``test_no_stage_5_to_9_production_package_
    imports_app_mt5``: no ``app/mt5`` module may import a Stage 5-9
    production package either - Stage 10 depends downward on Stage 5-9's
    output contracts only through the narrow, explicitly-approved
    ``app.core.models.position`` exception on ``app.mt5.tracker`` (see
    ``test_only_tracker_module_imports_position_record``), never on any
    Stage 5-9 *logic* package."""
    mt5_package_dir = REPO_ROOT / "app" / "mt5"
    stage_5_9_prefixes = tuple(package.replace("/", ".") for package in _STAGE_5_9_PACKAGES)
    for path in mt5_package_dir.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name.startswith(stage_5_9_prefixes)}
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import {offending}"


def test_history_module_source_never_mentions_position_record_or_risk_gate() -> None:
    source = inspect.getsource(app.mt5.history)
    for forbidden in ("PositionRecord", "AccountRiskSnapshot", "RiskGate"):
        assert forbidden not in source


def test_no_stage_10e_module_source_mentions_order_send_or_order_check() -> None:
    """Substring-safe (unlike the ``RiskGate``/``StatisticsAggregator``
    checks below, this repository's own module docstrings never have reason
    to discuss order placement in prose, so a plain substring check cannot
    false-positive here the way it would on a "never invokes X" docstring
    sentence)."""
    for module in (app.mt5.matching, app.mt5.tracker, app.mt5.recommendation_persistence):
        source = inspect.getsource(module)
        assert "order_send" not in source
        assert "order_check" not in source


def test_matching_module_never_mentions_position_record() -> None:
    """``app.mt5.matching`` produces only an ``MT5MatchResult`` - it never
    even needs to know ``PositionRecord`` exists (unlike ``app.mt5.tracker``,
    which legitimately does - see ``test_only_tracker_module_imports_
    position_record``)."""
    assert "PositionRecord" not in inspect.getsource(app.mt5.matching)


def test_recommendation_persistence_module_never_mentions_metatrader5() -> None:
    assert "MetaTrader5" not in inspect.getsource(app.mt5.recommendation_persistence)


def test_no_app_mt5_module_mentions_history_orders_get() -> None:
    mt5_package_dir = REPO_ROOT / "app" / "mt5"
    for path in mt5_package_dir.glob("*.py"):
        assert "history_orders_get" not in path.read_text(encoding="utf-8")


def test_tracker_reuses_stage_10d_pnl_classifier_rather_than_duplicating_it() -> None:
    """Stage 10E must not implement a second, conflicting per-deal
    financial classification - ``app.mt5.tracker`` is expected to literally
    import and call ``app.mt5.history.classify_trading_deal``."""
    tree = ast.parse(inspect.getsource(app.mt5.tracker))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.mt5.history":
            imported_names.update(alias.name for alias in node.names)
    assert "classify_trading_deal" in imported_names


def test_pure_stage_10e_modules_never_import_filesystem_or_metatrader5() -> None:
    for module in _PURE_STAGE_10E_MODULES:
        tree = ast.parse(inspect.getsource(module))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        assert names.isdisjoint({"pathlib", "os", "MetaTrader5", "app.mt5.client", "app.mt5.recommendation_persistence"})


def test_pure_stage_10e_modules_never_call_wall_clock_random_or_uuid() -> None:
    for module in _PURE_STAGE_10E_MODULES:
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"now", "utcnow", "uuid4"}, f"{module.__name__} must not read wall clock/generate UUIDs"
            if isinstance(node, ast.Name):
                assert node.id not in {"random", "uuid"}, f"{module.__name__} must not reference {node.id}"


def test_only_recommendation_persistence_module_touches_filesystem_among_new_stage_10e_modules() -> None:
    source = inspect.getsource(app.mt5.recommendation_persistence)
    assert "import os" in source or "from os" in source
    assert "Path" in source


def test_no_stage_10e_module_calls_aggregate_or_evaluate() -> None:
    """``.aggregate(``/``.evaluate(`` are ``StatisticsAggregator``'s and
    ``RiskGate``'s respective call sites - a plain substring check is safe
    here (no module docstring has reason to discuss calling either method in
    prose), complementing the robust import-based check in
    ``test_no_app_mt5_module_imports_account_risk_snapshot_or_risk_gate``."""
    for module in (app.mt5.matching, app.mt5.tracker, app.mt5.recommendation_persistence):
        source = inspect.getsource(module)
        assert ".aggregate(" not in source
        assert ".evaluate(" not in source


def test_app_execution_still_contains_only_init() -> None:
    package_dir = REPO_ROOT / "app" / "execution"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == ["__init__.py"]


def test_app_orchestration_contains_only_approved_decision_risk_pipeline_surface() -> None:
    """``app/orchestration`` previously contained only ``__init__.py``
    (Final Runtime Integration Part A audit's finding); Part B added
    ``facts.py`` (pure Runtime Fact Assembly only - see
    ``tests/test_orchestration_facts_module_hygiene.py`` for its own detailed
    purity/dependency checks); Part C adds the second approved production
    module, ``decision_risk_pipeline.py`` (pure Stage 5-9 orchestration only -
    see ``tests/test_decision_risk_pipeline_module_hygiene.py`` for its own
    detailed purity/dependency checks). This assertion intentionally still
    forbids any unapproved cycle/execution/tracking/feedback/API/Telegram/LLM
    orchestration module from appearing here."""
    package_dir = REPO_ROOT / "app" / "orchestration"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == ["__init__.py", "decision_risk_pipeline.py", "facts.py"]
