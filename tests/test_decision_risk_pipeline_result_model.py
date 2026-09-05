"""``DecisionRiskPipelineResult`` invariants: every valid/invalid COMPLETED
vs BLOCKED_BEFORE_RISK combination.

Reuses real ``DecisionRiskPipelineResult`` instances produced by the real
``evaluate_decision_risk_pipeline`` (one COMPLETED, one BLOCKED_BEFORE_RISK)
as a source of genuinely valid embedded fields, then recombines those fields
into the invalid combinations the model must reject - never a hand-rolled
``StrategySetupResult``/``StrategySessionResult``/``AccountRiskSnapshotAssembly``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline
from tests.decision_risk_pipeline_support import (
    NOW,
    blocked_assembly,
    context,
    ready_assembly,
    symbol_facts,
    trend_following_market_structure,
    trend_following_technical,
)
from tests.risk_gate_support import default_config


def _run(*, account_risk_snapshot_assembly):
    return evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=account_risk_snapshot_assembly,
        trading_cycle_config=default_config(),
    )


def _completed_result():
    return _run(account_risk_snapshot_assembly=ready_assembly())


def _blocked_result():
    return _run(account_risk_snapshot_assembly=blocked_assembly())


def test_completed_constructs() -> None:
    result = _completed_result()
    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    assert result.strategy_session_result is not None


def test_blocked_before_risk_constructs() -> None:
    result = _blocked_result()
    assert result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
    assert result.strategy_session_result is None


def test_completed_requires_session_result() -> None:
    completed = _completed_result()
    with pytest.raises(ValidationError):
        DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.COMPLETED,
            strategy_setup_result=completed.strategy_setup_result,
            account_risk_snapshot_assembly=completed.account_risk_snapshot_assembly,
            strategy_session_result=None,
        )


def test_completed_requires_ready_assembly() -> None:
    completed = _completed_result()
    blocked = _blocked_result()
    with pytest.raises(ValidationError):
        DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.COMPLETED,
            strategy_setup_result=completed.strategy_setup_result,
            account_risk_snapshot_assembly=blocked.account_risk_snapshot_assembly,
            strategy_session_result=completed.strategy_session_result,
        )


def test_blocked_before_risk_must_not_carry_session_result() -> None:
    completed = _completed_result()
    blocked = _blocked_result()
    with pytest.raises(ValidationError):
        DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK,
            strategy_setup_result=blocked.strategy_setup_result,
            account_risk_snapshot_assembly=blocked.account_risk_snapshot_assembly,
            strategy_session_result=completed.strategy_session_result,
        )


def test_blocked_before_risk_requires_blocked_assembly() -> None:
    completed = _completed_result()
    blocked = _blocked_result()
    with pytest.raises(ValidationError):
        DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK,
            strategy_setup_result=blocked.strategy_setup_result,
            account_risk_snapshot_assembly=completed.account_risk_snapshot_assembly,
            strategy_session_result=None,
        )


def test_outcome_always_derived_from_assembly_never_chosen_independently() -> None:
    """A READY assembly paired with ``BLOCKED_BEFORE_RISK`` (and no session
    result) must still be rejected - outcome is never an independent caller
    choice."""
    completed = _completed_result()
    with pytest.raises(ValidationError):
        DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK,
            strategy_setup_result=completed.strategy_setup_result,
            account_risk_snapshot_assembly=completed.account_risk_snapshot_assembly,
            strategy_session_result=None,
        )


def test_market_evaluation_recoverable_via_strategy_setup_result() -> None:
    """Confirms ``market_evaluation`` is not (and does not need to be) a
    separate top-level field - it is always reachable, unchanged, through
    ``strategy_setup_result``'s own nested chain."""
    result = _completed_result()
    market_evaluation = (
        result.strategy_setup_result.strategy_policy_result.strategy_judge_result.strategy_router_result.market_evaluation
    )
    assert market_evaluation is not None
