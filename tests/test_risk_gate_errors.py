"""Stage 7 caller/orchestration contract errors: unknown candidate family,
candidate for a Policy-blocked family, duplicate candidate family, and
missing candidate for an eligible family - all typed domain errors, never a
``BLOCKED_BY_RISK`` business outcome."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.risk_gate_result import CandidateRiskInput
from app.risk.engine import RiskGate
from app.risk.errors import (
    CandidateForBlockedFamilyError,
    DuplicateCandidateFamilyError,
    MissingCandidateForEligibleFamilyError,
    UnknownCandidateFamilyError,
)
from tests.market_evaluation_support import full_technical_result
from tests.policy_gate_support import route_judge_and_gate
from tests.risk_gate_support import default_account_snapshot, default_config


def _policy_result():
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    return policy_result


def test_unknown_candidate_family_error() -> None:
    """BREAKOUT is not eligible in a technical-only evaluation (no flow)."""
    policy_result = _policy_result()
    with pytest.raises(UnknownCandidateFamilyError):
        RiskGate().evaluate(
            strategy_policy_result=policy_result,
            account_snapshot=default_account_snapshot(),
            candidate_inputs=(
                CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("10")),
                CandidateRiskInput(family=StrategyFamily.EVENT_DRIVEN, risk_per_unit=Decimal("5")),
            ),
            trading_cycle_config=default_config(),
        )


def test_candidate_for_blocked_family_error() -> None:
    policy_result = _policy_result()
    with pytest.raises(CandidateForBlockedFamilyError):
        RiskGate().evaluate(
            strategy_policy_result=policy_result,
            account_snapshot=default_account_snapshot(),
            candidate_inputs=(
                CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("10")),
                CandidateRiskInput(family=StrategyFamily.MEAN_REVERSION, risk_per_unit=Decimal("5")),
            ),
            trading_cycle_config=default_config(),
        )


def test_duplicate_candidate_family_error() -> None:
    policy_result = _policy_result()
    with pytest.raises(DuplicateCandidateFamilyError):
        RiskGate().evaluate(
            strategy_policy_result=policy_result,
            account_snapshot=default_account_snapshot(),
            candidate_inputs=(
                CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("10")),
                CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("5")),
            ),
            trading_cycle_config=default_config(),
        )


def test_missing_candidate_for_eligible_family_error() -> None:
    policy_result = _policy_result()
    with pytest.raises(MissingCandidateForEligibleFamilyError):
        RiskGate().evaluate(
            strategy_policy_result=policy_result,
            account_snapshot=default_account_snapshot(),
            candidate_inputs=(),
            trading_cycle_config=default_config(),
        )
