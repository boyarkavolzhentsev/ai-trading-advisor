"""Stage 4G must never interpret individual Stage 4F dimensions.

Guards against reintroducing the contradiction/agreement subsystem that was
explicitly removed from the approved design: no
``SENTIMENT_PROVIDER_AGREEMENT`` promotion, no per-dimension special
handling, no ``ExternalIntelligenceDimension`` member referenced anywhere in
Stage 4G source, and no observation-content field on any Stage 4G model.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceDimension
from app.core.models.external_intelligence_supervisor_result import (
    ExternalIntelligenceScopeSummary,
    ExternalIntelligenceSupervisorResult,
)
from app.external_intelligence_supervisor import errors, protocols, supervisor

MODULES = (errors, protocols, supervisor)

FORBIDDEN_NAMES = tuple(member.value for member in ExternalIntelligenceDimension) + (
    "ExternalIntelligenceDimension",
    "SentimentAgreementVerdict",
    "SentimentSign",
)

FORBIDDEN_OBSERVATION_FIELDS = {
    "observations",
    "observation",
    "dimension",
    "sentiment_agreement",
    "news_sentiment_agreement",
    "agreement",
    "contradiction",
    "coherence",
}


_DOCSTRING_PATTERN = re.compile(r'"""(?:[^"]|"(?!""))*"""', re.DOTALL)


def _source_without_docstrings(module) -> str:
    """Strip triple-quoted docstrings before scanning.

    Design-report prose legitimately *names* forbidden dimensions to explain
    that they are deliberately not handled (e.g. "no ``SENTIMENT_PROVIDER_
    AGREEMENT`` promotion") - only a reference in actual code, not in
    documentation explaining an absence, indicates a boundary violation.
    """
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    return _DOCSTRING_PATTERN.sub("", source)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_dimension_vocabulary_referenced_in_source(module) -> None:
    source = _source_without_docstrings(module)
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in source, f"{module.__name__} references forbidden Stage 4F dimension vocabulary {forbidden!r}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_dimension_enum_imported(module) -> None:
    path = Path(inspect.getfile(module))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.names:
            for alias in node.names:
                assert alias.name not in {
                    "ExternalIntelligenceDimension",
                    "SentimentAgreementVerdict",
                    "SentimentSign",
                }, f"{module.__name__} imports forbidden dimension vocabulary {alias.name!r}"


def test_supervisor_result_has_no_observation_level_fields() -> None:
    assert FORBIDDEN_OBSERVATION_FIELDS.isdisjoint(ExternalIntelligenceSupervisorResult.model_fields)


def test_scope_summary_has_no_observation_level_fields() -> None:
    assert FORBIDDEN_OBSERVATION_FIELDS.isdisjoint(ExternalIntelligenceScopeSummary.model_fields)
