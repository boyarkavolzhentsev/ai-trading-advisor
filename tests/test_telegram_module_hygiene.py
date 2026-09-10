"""``app/telegram/*`` module-hygiene tests: no direct import of any closed
execution primitive; only the approved cross-boundary names reused."""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

_FORBIDDEN_IMPORTS = {
    "MT5Client",
    "BinanceRestClient",
    "OpenAIExplanationClient",
    "run_runtime_cycle",
    "Judge",
    "RiskGate",
    "PortfolioSupervisor",
    "SessionGate",
    "SetupConstruction",
    "ProductionAdvisoryComposer",
    "ProductionAdvisoryConfig",
}

_TELEGRAM_MODULES = [
    "app.telegram.config",
    "app.telegram.identity",
    "app.telegram.rendering",
    "app.telegram.handlers",
    "app.telegram.bot",
]


def _imported_names(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("module_name", _TELEGRAM_MODULES)
def test_telegram_modules_never_import_closed_execution_primitives(module_name: str) -> None:
    module = importlib.import_module(module_name)
    hit = _imported_names(module) & _FORBIDDEN_IMPORTS
    assert not hit, f"{module_name} imports forbidden execution primitives: {hit}"


@pytest.mark.parametrize("module_name", _TELEGRAM_MODULES)
def test_telegram_modules_never_import_fastapi(module_name: str) -> None:
    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("fastapi"):
            pytest.fail(f"{module_name} imports fastapi - no concrete architectural reason established")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("fastapi"), f"{module_name} imports fastapi"


def test_only_two_bootstrap_factories_are_imported_by_bot_module() -> None:
    """app.telegram.bot may reuse exactly the two approved
    app.bootstrap.production factory functions - never construct
    ProductionAdvisoryConfig/ProductionAdvisoryComposer itself."""
    import app.telegram.bot as bot_module

    tree = ast.parse(inspect.getsource(bot_module))
    bootstrap_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.bootstrap.production":
            bootstrap_imports.update(alias.asname or alias.name for alias in node.names)
    assert bootstrap_imports == {"build_production_advisory_config_from_env", "build_production_advisory_service"}


def test_no_trading_execution_method_names_appear_in_source() -> None:
    """AST-based attribute-access scan across every app/telegram/*.py file -
    never calls an order/position/execution-shaped method."""
    forbidden_attrs = {"order_send", "position_close", "position_modify", "order_cancel", "order_check"}
    for module_name in _TELEGRAM_MODULES:
        module = importlib.import_module(module_name)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr.lower() not in forbidden_attrs, f"{module_name} references {node.attr}"


def test_run_never_executes_at_import_time() -> None:
    """Importing app.telegram.bot must never call run() - proven by the
    module's own `if __name__ == "__main__":` guard; this test just proves
    the module imports without error and without hasattr side effects."""
    import app.telegram.bot as bot_module

    assert hasattr(bot_module, "run")
    assert hasattr(bot_module, "build_bot")
