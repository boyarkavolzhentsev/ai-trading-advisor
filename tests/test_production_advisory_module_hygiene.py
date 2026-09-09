"""Stage 0D Production Advisory Composition module-hygiene tests.

AST-based (not substring) throughout, so nothing here can false-positive on
an explanatory docstring/comment mentioning a forbidden name in prose -
mirrors ``tests/test_mt5_rollover_calculation.py``'s own established
precedent for this exact class of check.
"""

from __future__ import annotations

import ast
import inspect

import app.production_advisory.composer as composer_module
import app.production_advisory.config as config_module
import app.production_advisory.errors as errors_module
import app.production_advisory.lock as lock_module
import app.production_advisory.result as result_module

_ALL_MODULES = (composer_module, config_module, errors_module, lock_module, result_module)

_FORBIDDEN_EXECUTION_CALLS = {"OrderSend", "order_send", "positions_get_and_modify"}
_FORBIDDEN_IDENTITY_GENERATORS = {"uuid4", "uuid1", "uuid3", "uuid5", "random", "randint", "choice", "token_hex", "token_urlsafe"}


def _imported_module_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _called_names(module: object) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def test_no_forbidden_trading_execution_surface() -> None:
    for module in _ALL_MODULES:
        called = _called_names(module)
        assert called.isdisjoint(_FORBIDDEN_EXECUTION_CALLS), f"{module.__name__} calls a forbidden execution surface"


def test_no_ctrade_or_mt5_order_imports() -> None:
    for module in _ALL_MODULES:
        imported = _imported_module_names(module)
        assert not any("CTrade" in name for name in imported)
        assert not any(name.endswith(".order") for name in imported)


def test_no_uuid_random_or_secrets_identity_generation() -> None:
    """Stage0D generates no trade/cycle identity of its own - as_of and
    trade_ids are both caller-supplied on every run_cycle call."""
    for module in _ALL_MODULES:
        imported = _imported_module_names(module)
        assert imported.isdisjoint({"uuid", "random", "secrets"}), f"{module.__name__} imports an identity-generation module"
        called = _called_names(module)
        assert called.isdisjoint(_FORBIDDEN_IDENTITY_GENERATORS), f"{module.__name__} calls an identity-generation function"


def test_no_direct_judge_risk_portfolio_session_internals_import() -> None:
    """Stage0D must use run_runtime_cycle as the closed trading-engine
    seam - never import Judge/Risk/Portfolio/Session/SetupConstruction
    internals to reproduce their logic itself."""
    forbidden_modules = {
        "app.judge.judge",
        "app.risk.engine",
        "app.diversification.supervisor",
        "app.statistics.session",
        "app.decision.setup_construction",
        "app.decision.gate",
        "app.decision.high_impact_event_gate",
        "app.strategies.router",
        "app.market_evaluation.evaluator",
    }
    for module in _ALL_MODULES:
        imported = _imported_module_names(module)
        collision = imported & forbidden_modules
        assert not collision, f"{module.__name__} imports closed trading-engine internals: {collision}"


def test_composer_imports_run_runtime_cycle_as_its_sole_trading_engine_seam() -> None:
    imported = _imported_module_names(composer_module)
    assert "app.orchestration.runtime_cycle" in imported


def test_no_direct_metatrader5_import() -> None:
    for module in _ALL_MODULES:
        imported = _imported_module_names(module)
        assert "MetaTrader5" not in imported


def test_no_openai_sdk_direct_import() -> None:
    """Only the existing adapter/protocol seam - never the raw SDK."""
    for module in _ALL_MODULES:
        imported = _imported_module_names(module)
        assert "openai" not in imported
