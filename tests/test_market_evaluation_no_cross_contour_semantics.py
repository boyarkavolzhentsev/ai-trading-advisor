"""Stage 5A must never compare semantic content across contours.

Guards against reintroducing an agreement matrix, contradiction engine,
coherence/confluence score, or directional reconciliation between Flow,
Technical, and External Intelligence. Structural scope alignment (exact
identity matching against explicit context fields) is permitted and is not
what this guards against.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.market_evaluation import errors, evaluator, protocols

MODULES = (errors, evaluator, protocols)

_DOCSTRING_PATTERN = re.compile(r'"""(?:[^"]|"(?!""))*"""', re.DOTALL)

FORBIDDEN_SUBSTRINGS = (
    "agreement_matrix",
    "contradiction",
    "coherence",
    "confluence",
    "reconciliation",
    "TrendDirection",
    "PriceFlowRelationship",
    "SentimentSign",
    "SentimentAgreementVerdict",
    "AgreementVerdict",
    "TechnicalAgreementVerdict",
)

# Every dimension-carrying enum from Flow/Technical/External must never be
# imported into Stage 5A - it only ever inspects analyst_type/status/quality
# and native scope identity fields, never dimension/observation content.
FORBIDDEN_IMPORTS = (
    "app.core.enums.flow_analysis",
    "app.core.enums.technical_analysis",
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
    """Strip triple-quoted docstrings before scanning.

    Design-report prose legitimately *names* forbidden semantic concepts to
    explain that this package deliberately does not implement them (e.g.
    "no ... contradiction ... engine") - only a reference in actual code
    indicates a boundary violation.
    """
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    return _DOCSTRING_PATTERN.sub("", source)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_semantic_vocabulary_in_source(module) -> None:
    source = _source_without_docstrings(module)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in source, f"{module.__name__} references forbidden cross-contour semantic term {forbidden!r}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_dimension_enum_module_imported(module) -> None:
    _, imports = _source_and_imports(module)
    offending = imports & set(FORBIDDEN_IMPORTS)
    assert offending == set(), f"{module.__name__} imports forbidden dimension-vocabulary module(s): {offending}"


def test_result_has_no_agreement_or_coherence_field() -> None:
    forbidden = {"agreement", "coherence", "confluence", "contradiction", "reconciliation"}
    assert forbidden.isdisjoint(MarketEvaluationResult.model_fields)
