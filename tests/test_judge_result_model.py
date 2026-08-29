"""Stage 6B result-model self-validation: ``JudgeEvidenceRef``,
``JudgeFamilyResult`` and ``StrategyJudgeResult`` invariants, frozen/
extra-forbid behavior. Malformed externally-constructed objects must be
rejected - not only objects ``Judge`` itself would build."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.strategy_judge import DirectionalCandidate, EvidenceRole, JudgeContour, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.strategy_judge_result import JudgeEvidenceRef, JudgeFamilyResult, StrategyJudgeResult
from tests.market_evaluation_support import full_technical_result, make_context
from tests.strategy_router_support import evaluation
from app.strategies.router import StrategyRouter

_REF_A = JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=0, observation_index=0)
_REF_B = JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=0, observation_index=1)


# --- JudgeFamilyResult: direction/outcome coupling ---


def test_directional_requires_direction() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.DIRECTIONAL, direction=None)


def test_mixed_forbids_direction() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=JudgeOutcome.MIXED,
            direction=DirectionalCandidate.LONG_CANDIDATE,
            evidence_refs=(_REF_A, _REF_B),
        )


def test_insufficient_evidence_forbids_direction() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE,
            direction=DirectionalCandidate.LONG_CANDIDATE,
        )


def test_insufficient_evidence_forbids_nonempty_refs() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE, evidence_refs=(_REF_A,))


def test_directional_requires_at_least_one_primary_ref() -> None:
    corroborating_only = JudgeEvidenceRef(
        contour=JudgeContour.TECHNICAL, role=EvidenceRole.CORROBORATING, analyst_result_index=0, observation_index=0
    )
    with pytest.raises(ValidationError):
        JudgeFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=JudgeOutcome.DIRECTIONAL,
            direction=DirectionalCandidate.LONG_CANDIDATE,
            evidence_refs=(corroborating_only,),
        )


def test_mixed_requires_at_least_two_refs() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.MIXED, evidence_refs=(_REF_A,))


def test_mixed_with_zero_refs_rejected() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.MIXED, evidence_refs=())


def test_valid_directional_accepted() -> None:
    result = JudgeFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        outcome=JudgeOutcome.DIRECTIONAL,
        direction=DirectionalCandidate.LONG_CANDIDATE,
        evidence_refs=(_REF_A,),
    )
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


# --- JudgeEvidenceRef / evidence_refs shape ---


def test_duplicate_refs_rejected() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=JudgeOutcome.DIRECTIONAL,
            direction=DirectionalCandidate.LONG_CANDIDATE,
            evidence_refs=(_REF_A, _REF_A),
        )


def test_non_canonical_ref_order_rejected() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.MIXED, evidence_refs=(_REF_B, _REF_A))


def test_negative_index_rejected() -> None:
    with pytest.raises(ValidationError):
        JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=-1, observation_index=0)


def test_evidence_ref_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=0, observation_index=0, confidence=0.9)


def test_family_result_frozen() -> None:
    result = JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        result.outcome = JudgeOutcome.DIRECTIONAL


def test_family_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE, confidence=0.9)


# --- StrategyJudgeResult ---


def _base_router_result(**kwargs):
    return StrategyRouter().route(market_evaluation=evaluation(**kwargs))


def test_family_results_must_match_eligible_families() -> None:
    router_result = _base_router_result(technical=full_technical_result())
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=())


def test_family_results_reject_ineligible_family() -> None:
    router_result = _base_router_result(technical=full_technical_result())
    extra = JudgeFamilyResult(family=StrategyFamily.EVENT_DRIVEN, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    trend = JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    reversion = JudgeFamilyResult(family=StrategyFamily.MEAN_REVERSION, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(trend, reversion, extra))


def test_family_results_reject_wrong_order() -> None:
    router_result = _base_router_result(technical=full_technical_result())
    trend = JudgeFamilyResult(family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    reversion = JudgeFamilyResult(family=StrategyFamily.MEAN_REVERSION, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(reversion, trend))


def test_evidence_ref_out_of_bounds_analyst_result_index_rejected() -> None:
    router_result = _base_router_result(technical=full_technical_result())
    bad_ref = JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=9999, observation_index=0)
    trend = JudgeFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.DIRECTIONAL, direction=DirectionalCandidate.LONG_CANDIDATE, evidence_refs=(bad_ref,)
    )
    reversion = JudgeFamilyResult(family=StrategyFamily.MEAN_REVERSION, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(trend, reversion))


def test_evidence_ref_out_of_bounds_observation_index_rejected() -> None:
    router_result = _base_router_result(technical=full_technical_result())
    bad_ref = JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=EvidenceRole.PRIMARY, analyst_result_index=0, observation_index=9999)
    trend = JudgeFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.DIRECTIONAL, direction=DirectionalCandidate.LONG_CANDIDATE, evidence_refs=(bad_ref,)
    )
    reversion = JudgeFamilyResult(family=StrategyFamily.MEAN_REVERSION, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(trend, reversion))


def test_evidence_ref_to_unavailable_contour_rejected() -> None:
    """No flow was supplied - a FLOW-contour ref must be rejected."""
    router_result = _base_router_result(technical=full_technical_result())
    bad_ref = JudgeEvidenceRef(contour=JudgeContour.FLOW, role=EvidenceRole.PRIMARY, analyst_result_index=0, observation_index=0)
    trend = JudgeFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, outcome=JudgeOutcome.DIRECTIONAL, direction=DirectionalCandidate.LONG_CANDIDATE, evidence_refs=(bad_ref,)
    )
    reversion = JudgeFamilyResult(family=StrategyFamily.MEAN_REVERSION, outcome=JudgeOutcome.INSUFFICIENT_EVIDENCE)
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(trend, reversion))


def test_strategy_judge_result_frozen() -> None:
    router_result = _base_router_result()
    result = StrategyJudgeResult(strategy_router_result=router_result, family_results=())
    with pytest.raises(ValidationError):
        result.family_results = ()


def test_strategy_judge_result_extra_fields_forbidden() -> None:
    router_result = _base_router_result()
    with pytest.raises(ValidationError):
        StrategyJudgeResult(strategy_router_result=router_result, family_results=(), confidence=0.9)
