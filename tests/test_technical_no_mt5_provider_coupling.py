"""MT5 Price Authority Stage A contract correction: ``TechnicalProductionComposer``
and every other module under ``app/technical`` must remain provider-agnostic
- no import of the concrete MT5 OHLCV provider package, no textual mention
of ``MT5OHLCVProvider``, no provider-type branching of any kind. Broader
than ``tests/test_technical_production_module_hygiene.py`` (which scans only
``production.py`` for ``app.mt5``/``metatrader5``): this scans every file
under ``app/technical`` for the market-data provider package specifically,
proving Stage A introduced no coupling anywhere in the contour even though
Stage B (wiring) has not started."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "app" / "technical"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_module_imports_mt5_provider_package() -> None:
    for path in PACKAGE_DIR.rglob("*.py"):
        imports = _imports(path)
        offending = {
            name
            for name in imports
            if name == "app.market_data.providers.mt5" or name.startswith("app.market_data.providers.mt5.")
        }
        assert not offending, f"{path.relative_to(REPO_ROOT)} must not import the MT5 provider package: {offending}"


def test_no_module_mentions_mt5_provider_class_textually() -> None:
    for path in PACKAGE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "MT5OHLCVProvider" not in source, f"{path.relative_to(REPO_ROOT)} must not mention MT5OHLCVProvider"


def test_composer_never_isinstance_checks_a_concrete_provider_type() -> None:
    """No provider-type branching of any kind - the composer's own source
    must never call ``isinstance`` at all (it has no reason to distinguish
    provider types)."""
    import app.technical.production as production_module

    source = inspect.getsource(production_module)
    assert "isinstance(" not in source
