"""Deterministic Decision/Risk Pipeline (Final Runtime Integration, Part C).

Connects the already-produced, already-tested Stage 5-9 + Setup Construction
components into one pure orchestration sequence:

    Stage 5 Market Evaluation
    -> Stage 6A Strategy Router
    -> Stage 6B Judge
    -> Stage 6C Policy Gate
    -> Setup Construction
    -> Stage 7 Risk Gate
    -> Stage 8 Portfolio Supervisor
    -> Stage 9 Session Gate

Never reproduces any stage's own business logic: every call below passes an
already-produced typed result straight into the next stage's own existing
callable, exactly as each stage's own protocol declares it. Never invokes
``MT5Client``, rollover/recommendation persistence, ``app.mt5.risk``/
``app.mt5.history``/``app.mt5.sizing``/``app.mt5.matching``/``app.mt5.tracker``,
Stage 10C broker sizing, or Stage 10E recommendation tracking, never places or
checks an order, never reaches an execution/presentation surface of any kind,
and never reads the filesystem, the network, or the wall clock - a pure,
synchronous, stateless function of its explicit inputs only.

The one caller-supplied ``AccountRiskSnapshotAssembly`` (produced upstream by
Runtime Fact Assembly, outside this pipeline) is the only fail-closed branch:
Stage 5 through Setup Construction always run - they need no account-risk
fact at all - but Stage 7 Risk Gate onward runs only if the assembly is
``READY``. A ``BLOCKED`` assembly is never unwrapped into a fabricated,
zero-filled ``AccountRiskSnapshot``; the pipeline instead stops before Stage 7
and returns a ``BLOCKED_BEFORE_RISK`` result that preserves the assembly
object itself, unchanged, so its own ``reasons`` remain the sole, authoritative
explanation - never re-derived here.

Family identity is never matched by positional tuple index: this module never
constructs a cross-result mapping at all, because none is required - every
Stage 6A-9 result model already carries and validates ``StrategyFamily``
identity/order through its own embedded predecessor (see each stage's own
result-model docstring), and every call below simply forwards one stage's
typed output into the next stage's own typed input parameter.
"""

from __future__ import annotations

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyOutcome
from app.core.models.base import Timestamp
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.core.config.trading_cycle import TradingCycleConfig
from app.decision.gate import PolicyGate
from app.decision.setup_construction import SetupConstruction, to_candidate_risk_inputs
from app.diversification.supervisor import PortfolioSupervisor
from app.judge.judge import Judge
from app.market_evaluation.evaluator import MarketEvaluator
from app.risk.engine import RiskGate
from app.statistics.session import SessionGate
from app.strategies.router import StrategyRouter


def evaluate_decision_risk_pipeline(
    *,
    flow: FlowSupervisorResult | None,
    technical: TechnicalSupervisorResult | None,
    external: ExternalIntelligenceSupervisorResult | None,
    context: MarketEvaluationContext,
    evaluation_time: Timestamp,
    symbol_facts: MT5SymbolFacts | None,
    m15_market_structure: MarketStructureFeatures | None,
    account_risk_snapshot_assembly: AccountRiskSnapshotAssembly,
    trading_cycle_config: TradingCycleConfig,
    locked_override: bool = False,
) -> DecisionRiskPipelineResult:
    """Run one cycle's Stage 5-9 decision/risk chain.

    ``evaluation_time`` is the one coherent caller-supplied cycle timestamp:
    it is passed unchanged as Stage 5's own ``evaluation_time`` and as Setup
    Construction's own ``as_of`` - neither contract requires a second,
    independent timestamp, and no tolerance/coherence policy is invented
    between them.
    """
    market_evaluation = MarketEvaluator().evaluate(
        flow=flow,
        technical=technical,
        external=external,
        context=context,
        evaluation_time=evaluation_time,
    )
    strategy_router_result = StrategyRouter().route(market_evaluation=market_evaluation)
    strategy_judge_result = Judge().judge(strategy_router_result=strategy_router_result)
    strategy_policy_result = PolicyGate().apply(strategy_judge_result=strategy_judge_result)
    strategy_setup_result = SetupConstruction().construct(
        strategy_policy_result=strategy_policy_result,
        as_of=evaluation_time,
        symbol_facts=symbol_facts,
        m15_market_structure=m15_market_structure,
    )

    if account_risk_snapshot_assembly.outcome is not RuntimeFactAssemblyOutcome.READY:
        return DecisionRiskPipelineResult(
            outcome=DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK,
            strategy_setup_result=strategy_setup_result,
            account_risk_snapshot_assembly=account_risk_snapshot_assembly,
        )

    account_snapshot = account_risk_snapshot_assembly.account_snapshot
    assert account_snapshot is not None  # guaranteed by RuntimeFactAssemblyOutcome.READY

    candidate_risk_inputs = to_candidate_risk_inputs(strategy_setup_result)

    strategy_risk_result = RiskGate().evaluate(
        strategy_policy_result=strategy_policy_result,
        account_snapshot=account_snapshot,
        candidate_inputs=candidate_risk_inputs,
        trading_cycle_config=trading_cycle_config,
    )
    strategy_portfolio_result = PortfolioSupervisor().evaluate(strategy_risk_result=strategy_risk_result)
    strategy_session_result = SessionGate().evaluate(
        strategy_portfolio_result=strategy_portfolio_result,
        locked_override=locked_override,
    )

    return DecisionRiskPipelineResult(
        outcome=DecisionRiskPipelineOutcome.COMPLETED,
        strategy_setup_result=strategy_setup_result,
        account_risk_snapshot_assembly=account_risk_snapshot_assembly,
        strategy_session_result=strategy_session_result,
    )


__all__ = ["evaluate_decision_risk_pipeline"]
