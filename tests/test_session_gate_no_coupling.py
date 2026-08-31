"""Stage 9 ``app.statistics`` must remain an independent, backward-only
consumer of ``StrategyPortfolioResult``/``PositionRecord``.

No import edge into Stage 5-8 (``app.market_evaluation``/``app.strategies``/
``app.judge``/``app.decision``/``app.risk``/``app.money_management``/
``app.diversification``), Stage 10 (``app.mt5``/``app.execution``),
orchestration/evaluation, any LLM SDK, or any network/DB client.
``app.statistics`` reaches every upstream contract entirely through
``app.core`` - it never needs to import any producing package. No wall
clock, no ``random``, no ``uuid``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.statistics import aggregator, protocols, session

MODULES = (session, aggregator, protocols)

FORBIDDEN_MODULE_PREFIXES = (
    "app.market_evaluation",
    "app.strategies",
    "app.judge",
    "app.decision",
    "app.risk",
    "app.money_management",
    "app.diversification",
    "app.mt5",
    "app.execution",
    "app.orchestration",
    "app.evaluation",
    "app.llm",
    "app.telegram",
    "app.flow_supervisor",
    "app.technical_supervisor",
    "app.external_intelligence_supervisor",
    "app.external_intelligence_analysts",
    "app.technical_analysts",
    "app.flow_analysts",
)

ALLOWED_APP_IMPORT_PREFIXES = ("app.core.", "app.statistics.")

FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "httpx",
    "requests",
    "aiohttp",
    "websockets",
    "socket",
    "urllib",
    "sqlite3",
    "sqlalchemy",
    "pymongo",
    "psycopg2",
    "MetaTrader5",
    "random",
    "uuid",
)

FORBIDDEN_TIME_CALLS = ("datetime.now", "datetime.utcnow", "time.time", "time.monotonic", "time.perf_counter")


def _source_and_imports(module) -> tuple[str, set[str]]:
    path = Path(inspect.getfile(module))
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return source, imports


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_module_imported(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {name for name in imports if name.startswith(FORBIDDEN_MODULE_PREFIXES)}
    assert offending == set(), f"{module.__name__} imports forbidden module(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_only_depends_on_allowed_app_surface(module) -> None:
    _, imports = _source_and_imports(module)
    app_imports = {name for name in imports if name.startswith("app.")}
    disallowed = {name for name in app_imports if not name.startswith(ALLOWED_APP_IMPORT_PREFIXES)}
    assert disallowed == set(), f"{module.__name__} imports outside the allowed app surface: {disallowed}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_network_db_or_pseudo_random_import(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {name for name in imports if name.startswith(FORBIDDEN_IMPORT_PREFIXES)}
    assert offending == set(), f"{module.__name__} imports forbidden LLM/network/DB/random/uuid module(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_wall_clock_call(module) -> None:
    source, _ = _source_and_imports(module)
    tree = ast.parse(source)
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr_chain = []
            target = node.func
            while isinstance(target, ast.Attribute):
                attr_chain.append(target.attr)
                target = target.value
            if isinstance(target, ast.Name):
                attr_chain.append(target.id)
            calls.add(".".join(reversed(attr_chain)))
    offending = calls & set(FORBIDDEN_TIME_CALLS)
    assert offending == set(), f"{module.__name__} calls forbidden wall-clock API(s): {offending}"


def test_session_does_not_import_upstream_operational_packages() -> None:
    """SessionGate consumes StrategyPortfolioResult (an app.core.models
    contract) without ever needing to import app.risk, app.diversification,
    app.decision, app.judge or app.strategies themselves - it never reruns
    any upstream stage."""
    _, imports = _source_and_imports(session)
    for forbidden_prefix in ("app.risk", "app.diversification", "app.decision", "app.judge", "app.strategies"):
        assert not any(name == forbidden_prefix or name.startswith(forbidden_prefix + ".") for name in imports)


def test_aggregator_does_not_import_session_or_vice_versa() -> None:
    """Statistics and Session are decoupled: neither module imports the
    other, and neither imports app.mt5/app.execution."""
    session_source, session_imports = _source_and_imports(session)
    aggregator_source, aggregator_imports = _source_and_imports(aggregator)
    assert "app.statistics.aggregator" not in session_imports
    assert "app.statistics.session" not in aggregator_imports
    assert "StatisticsAggregator" not in session_source
    assert "PerformanceSnapshot" not in session_source
    assert "SessionGate" not in aggregator_source
