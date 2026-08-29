"""Stage 6A must never inspect semantic dimension/value content.

Guards against Strategy Router reading a Flow/Technical/External
Intelligence analyst observation's ``dimension``/``value``, or importing any
of their dimension-vocabulary enum modules. Structural participation/quality
inspection (already exercised by ``test_strategy_router_eligibility_rules``)
is what Stage 6A is *for* and is not what this guards against.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult
from app.strategies import protocols, router

MODULES = (router, protocols)

_DOCSTRING_PATTERN = re.compile(r'"""(?:[^"]|"(?!""))*"""', re.DOTALL)

FORBIDDEN_DIMENSION_MODULES = (
    "app.core.enums.flow_analysis",
    "app.core.enums.technical_analysis",
    "app.core.enums.external_intelligence_analysis",
)

FORBIDDEN_SUBSTRINGS = (
    "TrendDirection",
    "TakerFlowPressure",
    "OrderBookPressure",
    "LiquidationPressure",
    "PriceFlowRelationship",
    "SentimentSign",
    "SurpriseDirection",
    "AgreementVerdict",
    "TechnicalAgreementVerdict",
    "SentimentAgreementVerdict",
    "FundingSign",
    "BasisSign",
    "dimension",
    "observations",
    ".value",
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


def _source_without_docstrings(module) -> str:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    return _DOCSTRING_PATTERN.sub("", source)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_dimension_module_imported(module) -> None:
    _, imports = _source_and_imports(module)
    offending = imports & set(FORBIDDEN_DIMENSION_MODULES)
    assert offending == set(), f"{module.__name__} imports forbidden dimension-vocabulary module(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_semantic_vocabulary_in_source(module) -> None:
    source = _source_without_docstrings(module)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in source, f"{module.__name__} references forbidden dimension-content term {forbidden!r}"


def test_eligibility_entry_has_no_dimension_shaped_field() -> None:
    forbidden = {"dimension", "value", "observation", "observations", "evidence"}
    assert forbidden.isdisjoint(StrategyEligibilityEntry.model_fields)


def test_router_result_has_no_dimension_shaped_field() -> None:
    forbidden = {"dimension", "value", "observation", "observations", "evidence"}
    assert forbidden.isdisjoint(StrategyRouterResult.model_fields)
