"""Stage 6A ``app.strategies`` must remain an independent, backward-only
consumer of ``MarketEvaluationResult``.

No import edge into any Flow/Technical/External-Intelligence analyst or
supervisor package, the Stage 5A ``app.market_evaluation`` implementation
package, Stage 6B/6C, or any later layer (risk/money-management/
diversification/mt5/execution/orchestration/statistics/evaluation).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.strategies import protocols, router

MODULES = (router, protocols)

FORBIDDEN_MODULE_PREFIXES = (
    "app.flow.",
    "app.flow_analysts",
    "app.flow_supervisor",
    "app.technical.",
    "app.technical_analysts",
    "app.technical_supervisor",
    "app.external_intelligence_analysts",
    "app.external_intelligence_supervisor",
    "app.market_evaluation",
    "app.judge",
    "app.decision",
    "app.risk",
    "app.money_management",
    "app.diversification",
    "app.mt5",
    "app.execution",
    "app.orchestration",
    "app.statistics",
    "app.evaluation",
    "app.portfolio",
    "app.llm",
    "app.telegram",
)
FORBIDDEN_EXACT_MODULES = {"app.flow", "app.technical"}

ALLOWED_APP_IMPORT_PREFIXES = ("app.core.", "app.strategies.")


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
    offending = {
        name for name in imports if name in FORBIDDEN_EXACT_MODULES or name.startswith(FORBIDDEN_MODULE_PREFIXES)
    }
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
        "AgentAssessment",
        "TradeDirection",
        "RiskAssessment",
        "MoneyManagementDecision",
        "TradeSetup",
        "PositionRecord",
    )
    for forbidden in forbidden_names:
        assert forbidden not in source, f"{module.__name__} references forbidden legacy name {forbidden!r}"
