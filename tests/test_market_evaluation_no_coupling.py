"""Stage 5A must remain an independent contour, consuming only supervisor
result CONTRACTS through core models - never the supervisor packages
themselves, never any Flow/Technical/External-Intelligence analyst or
foundation package, never a later-layer or legacy Stage-0 package.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.market_evaluation import errors, evaluator, protocols

_DOCSTRING_PATTERN = re.compile(r'"""(?:[^"]|"(?!""))*"""', re.DOTALL)

MODULES = (errors, evaluator, protocols)

FORBIDDEN_MODULE_PREFIXES = (
    "app.flow_supervisor",
    "app.technical_supervisor",
    "app.external_intelligence_supervisor.supervisor",
    "app.external_intelligence_supervisor.errors",
    "app.flow.",
    "app.flow_analysts",
    "app.technical.",
    "app.technical_analysts",
    "app.external_intelligence_analysts",
    "app.macro",
    "app.rates",
    "app.news",
    "app.news_intel",
    "app.onchain",
    "app.evaluation",
    "app.judge",
    "app.decision",
    "app.strategies",
    "app.money_management",
    "app.risk",
    "app.portfolio",
    "app.execution",
)
FORBIDDEN_EXACT_MODULES = {
    "app.flow",
    "app.technical",
    "app.external_intelligence_supervisor",
    "app.core.models.assessment",
    "app.core.models.judge",
    "app.core.models.decision",
    "app.core.enums.trade",
}

ALLOWED_APP_IMPORT_PREFIXES = (
    "app.core.",
    "app.market_evaluation.",
)

FORBIDDEN_NAMES = (
    "AgentAssessment",
    "JudgeVerdict",
    "TradeDecision",
    "TradeDirection",
)
"""Deliberately excludes ``FlowSupervisor``/``TechnicalSupervisor``/
``ExternalIntelligenceSupervisor`` as bare substrings: each is a substring
of its own approved, legitimately-imported result contract
(``FlowSupervisorResult``/``TechnicalSupervisorResult``/
``ExternalIntelligenceSupervisorResult``), so a plain substring check would
false-positive on exactly the dependency Stage 5A is supposed to have.
``test_no_forbidden_module_imported``/``test_only_consumes_supervisor_result_contracts``
already guard against importing the actual supervisor *packages* precisely,
without this collision."""


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


def _source_without_docstrings(module) -> str:
    """Strip triple-quoted docstrings before scanning for forbidden names.

    Design-report prose legitimately *names* forbidden modules/classes to
    explain the boundary this package respects (e.g. "never
    ``FlowSupervisor``") - only a reference in actual code, not in
    documentation explaining an absence, indicates a coupling violation.
    """
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    return _DOCSTRING_PATTERN.sub("", source)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_name_referenced_in_source(module) -> None:
    source = _source_without_docstrings(module)
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in source, f"{module.__name__} references forbidden name {forbidden!r}"


def test_only_consumes_supervisor_result_contracts() -> None:
    """Stage 5A imports the three supervisor RESULT models (under
    app.core.models), never the supervisor packages/aggregate() methods
    themselves."""
    _, imports = _source_and_imports(evaluator)
    assert "app.core.models.flow_supervisor_result" in imports
    assert "app.core.models.technical_supervisor_result" in imports
    assert "app.core.models.external_intelligence_supervisor_result" in imports
    assert not any(name.startswith("app.flow_supervisor") for name in imports)
    assert not any(name.startswith("app.technical_supervisor") for name in imports)
    assert not any(name.startswith("app.external_intelligence_supervisor") for name in imports)


def test_app_evaluation_stub_untouched() -> None:
    """``app/evaluation/`` is a pre-existing, unrelated stub (post-trade
    review/learning) - Stage 5A must never repurpose or modify it."""
    path = Path("app/evaluation/__init__.py")
    source = path.read_text(encoding="utf-8")
    assert "post-trade" in source.lower()
    assert "market_evaluation" not in source
    assert "MarketEvaluat" not in source
