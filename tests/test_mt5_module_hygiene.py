"""Stage 10A/10B/10C dependency-boundary hygiene.

Only ``app.mt5.client`` may import ``MetaTrader5``; nothing in ``app.core``
or Stage 5-9 production packages may import ``app.mt5``; the protocol
exposes no order-placement/history surface; and ``app/mt5`` contains exactly
its approved Stage 10A + 10B + 10C file set (rollover transition/persistence,
open-risk assessment, broker sizing), with every later Stage 10D-E file name
still reserved."""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import app.mt5.client
import app.mt5.errors
import app.mt5.protocols
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
            "import app.mt5.risk; import app.mt5.sizing; "
            "import app.core.models.mt5_runtime; import app.core.enums.mt5_runtime; "
            "import app.core.models.mt5_rollover; import app.core.enums.mt5_rollover; import app.core.config.mt5_rollover; "
            "import app.core.models.mt5_position; import app.core.enums.mt5_position; "
            "import app.core.models.mt5_symbol; import app.core.enums.mt5_symbol; "
            "import app.core.models.mt5_sizing; import app.core.enums.mt5_sizing",
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


def test_protocol_exposes_no_order_placement_methods() -> None:
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    forbidden = {"order_send", "order_check", "open_positions", "symbol_specification", "history_deals", "history_orders"}
    assert members.isdisjoint(forbidden)


def test_protocol_exposes_exactly_the_approved_stage_10a_10b_10c_methods() -> None:
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    assert members == {"initialize", "runtime_status", "account_facts", "positions", "symbol_facts", "shutdown"}


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


def test_app_mt5_contains_only_approved_stage_10a_10b_10c_files() -> None:
    package_dir = REPO_ROOT / "app" / "mt5"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == [
        "__init__.py",
        "client.py",
        "errors.py",
        "persistence.py",
        "protocols.py",
        "risk.py",
        "rollover.py",
        "sizing.py",
    ]


def test_no_10d_through_10e_production_files_present() -> None:
    """No later Stage 10 sub-stage file (history/deal normalization,
    order/recommendation matching, position tracking) exists yet - 10A/10B/
    10C own exactly the connectivity/account-identity/rollover/open-
    risk/sizing surface. ``risk.py``/``sizing.py`` are now approved (Stage
    10C) and removed from this denylist; every other reserved name remains
    forbidden. ``models.py``/``enums.py``/``normalization.py`` remain
    forbidden permanently - domain models/enums live under ``app/core``,
    never under ``app/mt5`` (see Stage 10A/10B/10C precedent)."""
    package_dir = REPO_ROOT / "app" / "mt5"
    forbidden_names = {
        "models.py",
        "enums.py",
        "normalization.py",
        "history.py",
        "matching.py",
        "tracker.py",
    }
    present = {p.name for p in package_dir.glob("*.py")}
    assert present.isdisjoint(forbidden_names)


def test_app_execution_still_contains_only_init() -> None:
    package_dir = REPO_ROOT / "app" / "execution"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == ["__init__.py"]


def test_app_orchestration_still_contains_only_init() -> None:
    package_dir = REPO_ROOT / "app" / "orchestration"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == ["__init__.py"]
