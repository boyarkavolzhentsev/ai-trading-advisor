"""Stage 4G must remain an independent contour.

No import edge into Flow, Technical, any Stage 4A-4E foundation package, or
any later layer (evaluation/decision/judge/execution/risk/money-management/
diversification/portfolio/LLM/Telegram-API) from anywhere under
``app.external_intelligence_supervisor``. Stage 4F is Stage 4G's immediate
input boundary - no reaching past it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.external_intelligence_supervisor import errors, protocols, supervisor

MODULES = (errors, protocols, supervisor)

FORBIDDEN_MODULE_PREFIXES = (
    "app.flow.",
    "app.flow_analysts",
    "app.flow_supervisor",
    "app.technical.",
    "app.technical_analysts",
    "app.technical_supervisor",
    "app.macro",
    "app.rates",
    "app.news",
    "app.news_intel",
    "app.onchain",
    "app.evaluation",
    "app.decision",
    "app.judge",
    "app.execution",
    "app.risk",
    "app.money_management",
    "app.diversification",
    "app.portfolio",
    "app.llm",
    "app.telegram",
)
FORBIDDEN_EXACT_MODULES = {"app.flow", "app.technical"}

ALLOWED_APP_IMPORT_PREFIXES = (
    "app.core.",
    "app.external_intelligence_supervisor.",
    "app.external_intelligence_analysts.base",
    "app.external_intelligence_analysts.protocols",
)


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
def test_no_forbidden_model_name_referenced_in_source(module) -> None:
    source, _ = _source_and_imports(module)
    forbidden_names = (
        "FlowAnalysisResult",
        "FlowSupervisorResult",
        "TechnicalAnalysisResult",
        "TechnicalSupervisorResult",
        "TradeDecision",
        "JudgeVerdict",
        "RiskAssessment",
        "MoneyManagementDecision",
    )
    for forbidden in forbidden_names:
        assert forbidden not in source, f"{module.__name__} references forbidden name {forbidden!r}"
