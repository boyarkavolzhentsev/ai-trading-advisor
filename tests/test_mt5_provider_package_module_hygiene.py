"""``app/market_data/providers/mt5`` dependency-boundary hygiene (Stage A
corrective review, dependency-direction finding): market-data ingestion
infrastructure must not depend upward on ``app.technical`` merely to
determine generic candle closure - those primitives live at
``app.market_data.candle_time`` instead, a peer/lower-layer module."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "app" / "market_data" / "providers" / "mt5"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_module_imports_app_technical() -> None:
    for path in PACKAGE_DIR.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name == "app.technical" or name.startswith("app.technical.")}
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import app.technical: {offending}"


def test_no_module_imports_metatrader5() -> None:
    for path in PACKAGE_DIR.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if name == "MetaTrader5" or name.startswith("MetaTrader5.")}
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import MetaTrader5: {offending}"


def test_no_module_imports_binance() -> None:
    for path in PACKAGE_DIR.glob("*.py"):
        imports = _imports(path)
        offending = {name for name in imports if "binance" in name.lower()}
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import Binance specifics: {offending}"
