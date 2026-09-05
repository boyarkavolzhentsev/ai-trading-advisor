"""Decision/Risk Pipeline exact call-sequence proof.

Proves ``evaluate_decision_risk_pipeline`` invokes each existing Stage 5-9 +
Setup Construction component exactly once per cycle - and, on the
Runtime-Fact-Assembly-``BLOCKED`` path, that Stage 7/8/9 are never invoked at
all - by subclassing each real component to count real invocations while
delegating to the real (unmodified) implementation via ``super()``. Never
mocks away behavior: every counted call still runs the genuine stage logic.
"""

from __future__ import annotations

import pytest

import app.orchestration.decision_risk_pipeline as pipeline_module
from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
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


class _Counters:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def record(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1


@pytest.fixture
def counters(monkeypatch: pytest.MonkeyPatch) -> _Counters:
    counters = _Counters()

    RealMarketEvaluator = pipeline_module.MarketEvaluator
    RealStrategyRouter = pipeline_module.StrategyRouter
    RealJudge = pipeline_module.Judge
    RealPolicyGate = pipeline_module.PolicyGate
    RealSetupConstruction = pipeline_module.SetupConstruction
    RealRiskGate = pipeline_module.RiskGate
    RealPortfolioSupervisor = pipeline_module.PortfolioSupervisor
    RealSessionGate = pipeline_module.SessionGate

    class CountingMarketEvaluator(RealMarketEvaluator):
        def evaluate(self, **kwargs: object):  # type: ignore[override]
            counters.record("market_evaluator.evaluate")
            return super().evaluate(**kwargs)

    class CountingStrategyRouter(RealStrategyRouter):
        def route(self, **kwargs: object):  # type: ignore[override]
            counters.record("strategy_router.route")
            return super().route(**kwargs)

    class CountingJudge(RealJudge):
        def judge(self, **kwargs: object):  # type: ignore[override]
            counters.record("judge.judge")
            return super().judge(**kwargs)

    class CountingPolicyGate(RealPolicyGate):
        def apply(self, **kwargs: object):  # type: ignore[override]
            counters.record("policy_gate.apply")
            return super().apply(**kwargs)

    class CountingSetupConstruction(RealSetupConstruction):
        def construct(self, **kwargs: object):  # type: ignore[override]
            counters.record("setup_construction.construct")
            return super().construct(**kwargs)

    class CountingRiskGate(RealRiskGate):
        def evaluate(self, **kwargs: object):  # type: ignore[override]
            counters.record("risk_gate.evaluate")
            return super().evaluate(**kwargs)

    class CountingPortfolioSupervisor(RealPortfolioSupervisor):
        def evaluate(self, **kwargs: object):  # type: ignore[override]
            counters.record("portfolio_supervisor.evaluate")
            return super().evaluate(**kwargs)

    class CountingSessionGate(RealSessionGate):
        def evaluate(self, **kwargs: object):  # type: ignore[override]
            counters.record("session_gate.evaluate")
            return super().evaluate(**kwargs)

    monkeypatch.setattr(pipeline_module, "MarketEvaluator", CountingMarketEvaluator)
    monkeypatch.setattr(pipeline_module, "StrategyRouter", CountingStrategyRouter)
    monkeypatch.setattr(pipeline_module, "Judge", CountingJudge)
    monkeypatch.setattr(pipeline_module, "PolicyGate", CountingPolicyGate)
    monkeypatch.setattr(pipeline_module, "SetupConstruction", CountingSetupConstruction)
    monkeypatch.setattr(pipeline_module, "RiskGate", CountingRiskGate)
    monkeypatch.setattr(pipeline_module, "PortfolioSupervisor", CountingPortfolioSupervisor)
    monkeypatch.setattr(pipeline_module, "SessionGate", CountingSessionGate)

    return counters


def _run(*, account_risk_snapshot_assembly) -> object:
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


def test_completed_path_calls_every_stage_exactly_once(counters: _Counters) -> None:
    result = _run(account_risk_snapshot_assembly=ready_assembly())

    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    assert counters.counts == {
        "market_evaluator.evaluate": 1,
        "strategy_router.route": 1,
        "judge.judge": 1,
        "policy_gate.apply": 1,
        "setup_construction.construct": 1,
        "risk_gate.evaluate": 1,
        "portfolio_supervisor.evaluate": 1,
        "session_gate.evaluate": 1,
    }


def test_blocked_before_risk_path_never_calls_risk_portfolio_or_session(counters: _Counters) -> None:
    result = _run(account_risk_snapshot_assembly=blocked_assembly())

    assert result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
    assert counters.counts == {
        "market_evaluator.evaluate": 1,
        "strategy_router.route": 1,
        "judge.judge": 1,
        "policy_gate.apply": 1,
        "setup_construction.construct": 1,
    }
    assert "risk_gate.evaluate" not in counters.counts
    assert "portfolio_supervisor.evaluate" not in counters.counts
    assert "session_gate.evaluate" not in counters.counts
