"""Stage 7 result-model self-validation: ``AccountRiskSnapshot``,
``CandidateRiskInput``, ``RiskFamilyResult`` and ``StrategyRiskResult``
invariants, frozen/extra-forbid behavior. Malformed externally-constructed
objects must be rejected - not only objects ``RiskGate`` itself would build."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict, RiskGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.risk_gate_result import CandidateRiskInput, RiskFamilyResult, StrategyRiskResult
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, default_candidates_for, default_config
from tests.policy_gate_support import route_judge_and_gate

# --- RiskFamilyResult: verdict/reasons coupling ---


def test_eligible_forbids_reasons() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
            reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED,),
            max_individual_risk=Decimal("100"),
            recommended_units=Decimal("10"),
        )


def test_blocked_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=())


def test_eligible_requires_positive_sizing_fields() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW)


def test_eligible_rejects_zero_max_individual_risk() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
            max_individual_risk=Decimal("0"),
            recommended_units=Decimal("10"),
        )


def test_blocked_forbids_sizing_fields() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED,),
            max_individual_risk=Decimal("100"),
        )


def test_eligible_with_valid_sizing_accepted() -> None:
    result = RiskFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
        max_individual_risk=Decimal("500"),
        recommended_units=Decimal("50"),
    )
    assert result.max_individual_risk == Decimal("500")


# --- reasons: canonical order / duplicate-free / exclusivity ---


def test_duplicate_reasons_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED, RiskBlockReason.DAILY_LOSS_LIMIT_REACHED),
        )


def test_non_canonical_reason_order_rejected() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED, RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT),
        )


def test_policy_not_eligible_must_be_sole_reason() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.POLICY_NOT_ELIGIBLE, RiskBlockReason.DAILY_LOSS_LIMIT_REACHED),
        )


def test_daily_and_insufficient_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED, RiskBlockReason.INSUFFICIENT_REMAINING_RISK_BUDGET),
        )


# --- frozen / extra-forbid ---


def test_family_result_frozen() -> None:
    result = RiskFamilyResult(family=StrategyFamily.TREND_FOLLOWING, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=(RiskBlockReason.POLICY_NOT_ELIGIBLE,))
    with pytest.raises(ValidationError):
        result.verdict = RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW


def test_family_result_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        RiskFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.POLICY_NOT_ELIGIBLE,),
            confidence=0.9,
        )


def test_candidate_risk_input_frozen() -> None:
    candidate = CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("10"))
    with pytest.raises(ValidationError):
        candidate.risk_per_unit = Decimal("20")


def test_candidate_risk_input_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("10"), entry_price=Decimal("100"))


# --- StrategyRiskResult: family coverage / candidate coverage / outcome ---


def _base_policy_result():
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    return policy_result


def test_family_results_must_match_policy_family_results() -> None:
    policy_result = _base_policy_result()
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=policy_result,
            trading_cycle_config=default_config(),
            account_snapshot=default_account_snapshot(),
            candidate_inputs=default_candidates_for(policy_result),
            outcome=RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY,
            family_results=(),
        )


def test_duplicate_candidate_inputs_rejected_at_model_level() -> None:
    policy_result = _base_policy_result()
    duplicated = default_candidates_for(policy_result) * 2
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=policy_result,
            trading_cycle_config=default_config(),
            account_snapshot=default_account_snapshot(),
            candidate_inputs=duplicated,
            outcome=RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW,
            family_results=(),
        )


def test_candidate_for_non_eligible_family_rejected_at_model_level() -> None:
    policy_result = _base_policy_result()
    bad_candidates = (CandidateRiskInput(family=StrategyFamily.MEAN_REVERSION, risk_per_unit=Decimal("10")),)
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=policy_result,
            trading_cycle_config=default_config(),
            account_snapshot=default_account_snapshot(),
            candidate_inputs=bad_candidates,
            outcome=RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY,
            family_results=(),
        )


def test_inconsistent_top_level_outcome_rejected() -> None:
    from app.risk.engine import RiskGate

    policy_result = _base_policy_result()
    correct = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    wrong_outcome = (
        RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY
        if correct.outcome is RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW
        else RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW
    )
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=correct.strategy_policy_result,
            trading_cycle_config=correct.trading_cycle_config,
            account_snapshot=correct.account_snapshot,
            candidate_inputs=correct.candidate_inputs,
            outcome=wrong_outcome,
            family_results=correct.family_results,
        )


def test_mismatched_max_individual_risk_rejected() -> None:
    from app.risk.engine import RiskGate

    policy_result = _base_policy_result()
    correct = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    tampered_results = tuple(
        RiskFamilyResult(
            family=r.family,
            verdict=r.verdict,
            reasons=r.reasons,
            max_individual_risk=(r.max_individual_risk + Decimal("1") if r.max_individual_risk is not None else None),
            recommended_units=r.recommended_units,
        )
        for r in correct.family_results
    )
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=correct.strategy_policy_result,
            trading_cycle_config=correct.trading_cycle_config,
            account_snapshot=correct.account_snapshot,
            candidate_inputs=correct.candidate_inputs,
            outcome=correct.outcome,
            family_results=tampered_results,
        )


def test_frozen() -> None:
    from app.risk.engine import RiskGate

    policy_result = _base_policy_result()
    result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    with pytest.raises(ValidationError):
        result.outcome = RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY


def test_extra_fields_forbidden() -> None:
    policy_result = _base_policy_result()
    with pytest.raises(ValidationError):
        StrategyRiskResult(
            strategy_policy_result=policy_result,
            trading_cycle_config=default_config(),
            account_snapshot=default_account_snapshot(),
            candidate_inputs=default_candidates_for(policy_result),
            outcome=RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW,
            family_results=(),
            confidence=0.9,
        )
