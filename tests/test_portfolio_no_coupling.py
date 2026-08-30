"""Stage 8 ``app.diversification`` must remain an independent, backward-only
consumer of ``StrategyRiskResult``.

No import edge into Stage 7 (``app.risk``/``app.money_management``), Stage 6
(``app.decision``/``app.judge``/``app.strategies``), Stage 5
(``app.market_evaluation``), Stage 9 (``app.statistics``), Stage 10
(``app.mt5``/``app.execution``), orchestration/evaluation, any LLM SDK, or
any network client. ``app.diversification`` reaches every upstream contract
entirely through ``app.core.models`` - it never needs to import any
producing package.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.diversification import protocols, supervisor

MODULES = (supervisor, protocols)

FORBIDDEN_MODULE_PREFIXES = (
    "app.risk",
    "app.money_management",
    "app.decision",
    "app.judge",
    "app.strategies",
    "app.market_evaluation",
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

ALLOWED_APP_IMPORT_PREFIXES = ("app.core.", "app.diversification.")

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


def test_supervisor_does_not_import_risk_or_decision_packages() -> None:
    """PortfolioSupervisor consumes StrategyRiskResult (an app.core.models
    contract) without ever needing to import app.risk or app.decision
    themselves - it never reruns Risk or Policy Gate."""
    _, imports = _source_and_imports(supervisor)
    assert not any(name == "app.risk" or name.startswith("app.risk.") for name in imports)
    assert not any(name == "app.decision" or name.startswith("app.decision.") for name in imports)
