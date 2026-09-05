"""Decision/Risk Pipeline output contract.

Aggregates one cycle's Stage 5 Market Evaluation through Stage 9 Session Gate
run into one typed, lossless result. Never a duplicate domain model: every
field is either an unchanged embedding of an already-produced Stage 5-9 /
Runtime Fact Assembly result, or the coarse ``DecisionRiskPipelineOutcome``
describing how far the cycle got - no new evidence, direction, account
state, or risk figure is ever computed or copied out in isolation here.

``market_evaluation`` is deliberately not a separate top-level field: it is
already fully recoverable, unchanged, via
``strategy_setup_result.strategy_policy_result.strategy_judge_result.strategy_router_result.market_evaluation``
- Setup Construction always runs regardless of ``outcome`` (see the approved
Decision/Risk Pipeline design), so that path is always populated. Duplicating
it as a second top-level field would carry no independent information,
mirroring every Stage 5-9 result model's own "embed the input unchanged,
never copy a fact out in isolation" discipline one layer up.

``strategy_session_result`` is present if and only if ``outcome`` is
``COMPLETED``: it is the sole carrier of the Stage 7/8/9 audit chain, since
Stage 7 onward never runs when Runtime Fact Assembly is not ``READY``.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyOutcome
from app.core.models.base import DomainModel
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from app.core.models.session_result import StrategySessionResult
from app.core.models.setup_construction import StrategySetupResult


class DecisionRiskPipelineResult(DomainModel):
    """Deterministic aggregation of one Decision/Risk Pipeline cycle run.

    ``strategy_setup_result`` and ``account_risk_snapshot_assembly`` are
    always present - Stage 5 through Setup Construction always run, and
    Runtime Fact Assembly (produced upstream of this pipeline, supplied
    unchanged) always resolves to a value, regardless of ``outcome``.
    """

    outcome: DecisionRiskPipelineOutcome
    strategy_setup_result: StrategySetupResult
    account_risk_snapshot_assembly: AccountRiskSnapshotAssembly
    strategy_session_result: StrategySessionResult | None = None

    @model_validator(mode="after")
    def _validate_outcome_matches_assembly(self) -> Self:
        assembly_ready = self.account_risk_snapshot_assembly.outcome is RuntimeFactAssemblyOutcome.READY
        expected = (
            DecisionRiskPipelineOutcome.COMPLETED if assembly_ready else DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
        )
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match assembly-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_session_result_presence(self) -> Self:
        if self.outcome is DecisionRiskPipelineOutcome.COMPLETED:
            if self.strategy_session_result is None:
                raise ValueError("COMPLETED requires strategy_session_result")
        elif self.strategy_session_result is not None:
            raise ValueError("BLOCKED_BEFORE_RISK must not carry strategy_session_result")
        return self


__all__ = ["DecisionRiskPipelineResult"]
