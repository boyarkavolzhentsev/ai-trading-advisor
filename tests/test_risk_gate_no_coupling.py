"""Stage 7 ``app.risk``/``app.money_management`` must remain independent,
backward-only consumers of ``StrategyPolicyResult``.

No import edge into Stage 6B/6C (``app.judge``/``app.decision``), Stage 6A
(``app.strategies``), Stage 5 (``app.market_evaluation``), Stage 8
(``app.diversification``/``app.portfolio``), Stage 10 (``app.mt5``/
``app.execution``), orchestration/statistics/evaluation, any LLM SDK, or any
network client. Neither package needs to import ``app.decision`` itself -
both consume ``StrategyPolicyResult`` entirely through ``app.core.models``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.money_management import sizing
from app.risk import engine, errors, protocols

MODULES = (engine, errors, protocols, sizing)

FORBIDDEN_MODULE_PREFIXES = (
    "app.decision",
    "app.judge",
    "app.strategies",
    "app.market_evaluation",
    "app.diversification",
    "app.portfolio",
    "app.mt5",
    "app.execution",
    "app.orchestration",
    "app.statistics",
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

ALLOWED_APP_IMPORT_PREFIXES = ("app.core.", "app.risk.", "app.money_management.")

FORBIDDEN_IMPORT_PREFIXES = ("openai", "anthropic", "httpx", "requests", "aiohttp", "websockets", "socket", "urllib")


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
def test_no_forbidden_legacy_name_referenced_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    forbidden_names = (
        "TradeDecision",
        "JudgeVerdict",
        "JudgeVerdictType",
        "AgentAssessment",
        "TradeDirection",
        "RiskAssessment",
        "MoneyManagementDecision",
        "TradeSetup",
        "PositionRecord",
    )
    for forbidden in forbidden_names:
        assert forbidden not in source, f"{module.__name__} references forbidden legacy name {forbidden!r}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_llm_or_network_import(module) -> None:
    _, imports = _source_and_imports(module)
    offending = {name for name in imports if name.startswith(FORBIDDEN_IMPORT_PREFIXES)}
    assert offending == set(), f"{module.__name__} imports forbidden LLM/network module(s): {offending}"


def test_engine_does_not_import_decision_package() -> None:
    """RiskGate consumes StrategyPolicyResult (an app.core.models contract)
    without ever needing to import app.decision itself - it never reruns
    Policy Gate."""
    _, imports = _source_and_imports(engine)
    assert not any(name == "app.decision" or name.startswith("app.decision.") for name in imports)
