"""Stage 7 must never inspect market/Judge semantic content: no direction
vocabulary, no observation-value inspection, no import of any semantic
Stage 5/6B enum or model."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.risk import engine


def test_engine_never_imports_semantic_enums_or_models() -> None:
    path = Path(inspect.getfile(engine))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)

    forbidden_names = {
        "DirectionalCandidate",
        "JudgeContour",
        "EvidenceRole",
        "JudgeOutcome",
        "JudgeFamilyResult",
        "JudgeEvidenceRef",
        "StrategyJudgeResult",
        "MarketEvaluationResult",
        "TechnicalSupervisorResult",
        "FlowSupervisorResult",
        "ExternalIntelligenceSupervisorResult",
    }
    offending = imported_names & forbidden_names
    assert offending == set(), f"engine.py imports semantic Stage 5/6B name(s): {offending}"


def test_engine_source_never_references_directional_vocabulary() -> None:
    path = Path(inspect.getfile(engine))
    source = path.read_text(encoding="utf-8")
    for forbidden in ("LONG_CANDIDATE", "SHORT_CANDIDATE", "DirectionalCandidate"):
        assert forbidden not in source, f"engine.py references forbidden directional vocabulary: {forbidden!r}"
