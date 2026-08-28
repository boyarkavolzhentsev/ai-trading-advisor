"""Stage 4F must never interpret facts into a final trading conclusion, must
never depend on Stage 4G or any later layer, and must never carry a generic
provenance/metadata bag - all explicitly reviewed constraints from the
Stage 4F design and its implementation clarifications.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.external_intelligence_analysts import base, config, macro_event, news_sentiment, on_chain, protocols, rates_yield

MODULES = (base, config, protocols, macro_event, rates_yield, news_sentiment, on_chain)
MODEL_CLASSES = (ExternalIntelligenceEvidence, ExternalIntelligenceAnalysisObservation, ExternalIntelligenceAnalysisResult)

FORBIDDEN_TERMS = (
    "risk_on",
    "risk_off",
    "risk-on",
    "risk-off",
    "accumulation",
    "distribution",
    "recommendation",
    "final_direction",
    "market_direction",
    "trading_signal",
    "global_score",
    "composite_score",
    "external_score",
)
"""Deliberately excludes "semantic" (established fingerprint/timestamp
vocabulary carve-out, mirroring every prior stage's no-interpretation test),
"importance" (a real, spec-approved ``EVENT_IMPORTANCE`` dimension and
``EconomicEvent.importance`` field access - not an interpretation term here),
and "bullish"/"bearish" (used only in negation prose explaining their
absence, e.g. "never mapped to bullish/bearish") - enforcement for
bullish/bearish belongs on the bare-enum-value check in
``test_external_intelligence_no_trading_fields.py``, never on blanket
text scanning."""

FORBIDDEN_FIELDS = {
    "confidence",
    "strength",
    "reliability",
    "credibility",
    "metadata",
    "origin",
    "final_direction",
    "market_direction",
    "recommendation",
}
"""Deliberately excludes "provenance" as a blanket field-name ban:
``ExternalIntelligenceEvidence.provenance: str`` is a legitimate, approved
field (mirrors ``FlowEvidence``/``TechnicalEvidence``'s own ``provenance``
string field) - what required clarification 2 actually forbids is a
*dict-typed* provenance/metadata bag on the shared Result model, checked
precisely by type in ``test_result_has_no_generic_provenance_or_metadata_dict``
below, never a blanket name ban that would also catch Evidence's own
unrelated, approved string field."""


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_interpretation_vocabulary_in_source(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8").lower()
    offenders = [term for term in FORBIDDEN_TERMS if term in source]
    assert offenders == [], f"{module.__name__} contains forbidden interpretation term(s): {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_no_interpretation_or_provenance_bag_fields_on_models(model_cls) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(model_cls.model_fields)


def test_result_has_no_generic_provenance_or_metadata_dict() -> None:
    """Required clarification 2: no dict/metadata bag field of any kind on
    the shared Result model - traceability lives entirely in structured
    ``ExternalIntelligenceEvidence``."""
    for field_name, field_info in ExternalIntelligenceAnalysisResult.model_fields.items():
        assert field_info.annotation is not dict, f"{field_name} is dict-typed - a provenance bag is forbidden"


def test_no_stage_4g_supervisor_import_or_reference() -> None:
    forbidden_names = ("ExternalIntelligenceSupervisor", "Stage4G", "SupervisorResult")
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        for name in forbidden_names:
            assert name not in source, f"{module.__name__} references forbidden Stage 4G name {name!r}"


def test_no_decision_judge_execution_risk_import() -> None:
    forbidden_module_prefixes = ("app.decision", "app.judge", "app.execution", "app.risk", "app.money_management")
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        offending = {name for name in imports if any(name.startswith(prefix) for prefix in forbidden_module_prefixes)}
        assert offending == set(), f"{module.__name__} imports forbidden layer(s): {offending}"


def test_no_orchestration_or_portfolio_import() -> None:
    forbidden_module_prefixes = ("app.orchestration", "app.diversification", "app.evaluation")
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        offending = {name for name in imports if any(name.startswith(prefix) for prefix in forbidden_module_prefixes)}
        assert offending == set(), f"{module.__name__} imports forbidden layer(s): {offending}"


def test_no_partial_feature_quality_value_appears_as_a_literal_in_source() -> None:
    """Required clarification 4: Stage 4F V1 must never emit PARTIAL -
    checked at the source level that no *analyst* module constructs
    ``FeatureQuality.PARTIAL``. ``base.py`` is deliberately excluded: its
    ``_SEVERITY`` fold references every ``FeatureQuality`` member, including
    ``PARTIAL``, purely so the severity ordering stays correct and complete
    for the whole enum, not because Stage 4F emits it - see
    ``app.external_intelligence_analysts.base``'s docstring."""
    for module in (macro_event, rates_yield, news_sentiment, on_chain):
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert "PARTIAL" not in source, f"{module.__name__} references FeatureQuality.PARTIAL"


def test_base_module_constructs_partial_only_in_the_severity_fold() -> None:
    """Confirms the one intentional exception above is exactly what it
    claims to be - ``FeatureQuality.PARTIAL`` is referenced as a real value
    exactly once in ``base.py`` (the ``_SEVERITY`` dict entry); any other
    mention of the word is prose, not code that could construct or return
    it."""
    source = inspect.getsource(base)
    code_references = [line for line in source.splitlines() if "FeatureQuality.PARTIAL" in line]
    assert len(code_references) == 1
    assert "_SEVERITY" not in code_references[0]


def test_no_quality_module_exists() -> None:
    for model_cls in MODEL_CLASSES:
        assert "is_stale" not in model_cls.model_fields


def test_no_activity_flow_relationship_or_composite_dimension_exists() -> None:
    """Required correction: network-activity direction and exchange
    net-flow direction have no factually-grounded deterministic
    relationship in the Stage 4A-4E foundations - either combination (e.g.
    increasing activity with net inflow, or with net outflow) can occur for
    unrelated reasons, so no dimension, enum, or lookup table may map them
    onto AGREEMENT/DIVERGENCE (or any other composite/correlation/weighted
    concept). ACTIVITY_TREND and EXCHANGE_NET_FLOW must remain independent."""
    from app.core.enums import external_intelligence_analysis as ei_enums
    from app.core.enums.external_intelligence_analysis import ExternalIntelligenceDimension

    forbidden_dimension_names = {
        "ACTIVITY_FLOW_RELATIONSHIP",
        "ACTIVITY_FLOW_CORRELATION",
        "ACTIVITY_FLOW_SCORE",
        "COMPOSITE_ONCHAIN_SCORE",
    }
    assert forbidden_dimension_names.isdisjoint({m.name for m in ExternalIntelligenceDimension})

    forbidden_enum_class_names = {"ActivityFlowRelationship", "ActivityFlowCorrelation", "OnChainCompositeScore"}
    assert forbidden_enum_class_names.isdisjoint(dir(ei_enums))

    for module in MODULES:
        assert not hasattr(module, "_RELATIONSHIP_MAP")
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert "ACTIVITY_FLOW_RELATIONSHIP" not in source
        assert "ActivityFlowRelationship" not in source
