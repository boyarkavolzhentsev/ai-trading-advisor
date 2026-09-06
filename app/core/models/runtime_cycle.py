"""Deterministic Runtime Cycle Orchestration output contracts (Final Runtime
Integration, Part F).

Every field is either a direct, unchanged reference to an already-existing
Stage 10A-E/Runtime-Fact-Assembly/Decision-Risk-Pipeline/Final-Recommendation/
Part-E result object, or a narrow, Part-F-owned orchestration-level status
fact this stage's own coordinator needs to report - never a duplicate of any
nested model's own fields, and never a new financial/matching/risk
computation. ``RuntimeCycleResult`` deliberately carries many fields as
optional/empty: a genuinely partial, degraded, or blocked cycle must remain
fully inspectable rather than collapsing into an all-or-nothing result (see
the approved Part F design).

``PositionsReadStatus``/``HistoryReadStatus`` are locally-owned copies of
``app.mt5.risk.MT5PositionsReadStatus``/``app.mt5.history.MT5HistoryReadStatus``
- not imported from either (mirroring the Stage 10B/10C/10D/10E precedent of
maintaining independent copies of the same primitive rather than
cross-importing an impure-adjacent module's alias into ``app.core.models``).
"""

from __future__ import annotations

from typing import Literal

from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_runtime import AccountPositionMode
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.final_recommendation import FinalRecommendationConstructionResult
from app.core.models.mt5_history import MT5RealizedDailyPnLAssessment
from app.core.models.mt5_position import MT5OpenRiskAssessment
from app.core.models.mt5_rollover import MT5RolloverSnapshot
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.core.models.mt5_tracking import MT5TrackedRecommendation
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from app.core.models.tracking_integration import TrackedRecommendationConstructionResult

PositionsReadStatus = Literal["OK", "UNAVAILABLE", "UNMAPPABLE_POSITION_SIDE"]
HistoryReadStatus = Literal["OK", "UNAVAILABLE", "MALFORMED_TIMESTAMP"]


class NettingGuardResult(DomainModel):
    """One evaluation of Part F's own NETTING/UNKNOWN issuance guard for one
    target symbol this cycle - never evaluated for ``AccountPositionMode.HEDGING``."""

    symbol: Symbol
    account_position_mode: AccountPositionMode
    outcome: NettingIssuanceOutcome


class ExcludedTrackedRecommendation(DomainModel):
    """One persisted ``trade_id`` this cycle's coordinator could not safely
    load - corruption isolation preserved: this ``trade_id`` alone is
    excluded from advancement and from ``already_claimed_position_ids``
    accounting, every other ``trade_id`` proceeds normally."""

    trade_id: str
    read_status: Literal["CORRUPT", "UNAVAILABLE"]


class AdvancedTrackedRecommendationOutcome(DomainModel):
    """One existing tracked recommendation's result after one
    ``advance_tracked_recommendation`` call this cycle, plus whether the
    updated state was successfully persisted."""

    trade_id: str
    tracked_recommendation: MT5TrackedRecommendation
    persisted: bool


class TrackingIssuancePersistenceOutcome(DomainModel):
    """One newly-issued recommendation's persistence outcome this cycle.

    ``tracking_persisted``/``provenance_persisted`` are both ``False`` (never
    attempted) when ``tracking_creation_outcome`` is
    ``SNAPSHOT_UNAVAILABLE`` - there is nothing to persist. When ``CREATED``,
    each write is attempted independently (no distributed transaction, no
    rollback of a successful independent write) - all four success/failure
    combinations across the two are representable here.
    """

    trade_id: str
    tracking_creation_outcome: MT5TrackedRecommendationCreationOutcome
    tracking_persisted: bool
    provenance_persisted: bool


class RuntimeCycleResult(DomainModel):
    """Part F's complete, typed, single-cycle audit record.

    ``account_risk_snapshot_assembly`` is populated only once every one of
    ``rollover_snapshot``/``realized_daily_pnl_assessment``/
    ``open_risk_assessment`` was itself legitimately computed (its own
    underlying MT5 read confirmed ``"OK"``/account facts available) - this
    coordinator never fabricates a substitute for any of the three by
    inventing a block reason no existing Stage 10B/10C/10D vocabulary
    defines. Each of the three sub-assessments is still independently
    reported when only some of them could be computed, preserving partial
    audit visibility even when the overall assembly could not be attempted.

    ``target_symbol_facts_available`` makes one specific, otherwise-invisible
    failure mode directly observable rather than inferable: ``None`` means
    the cycle never reached symbol-facts acquisition at all (MT5 connectivity
    itself was unavailable - see ``outcome is RuntimeCycleOutcome.BLOCKED``);
    ``True``/``False`` means ``client.symbol_facts(target_symbol)`` was
    actually attempted and returned a fact/``None`` respectively. Without
    this field, a caller could only infer "target symbol facts were
    unavailable" by noticing ``decision_risk_pipeline_result is not None``
    (Stage 5-9 ran) alongside ``final_recommendation_construction_result is
    None`` (Final Recommendation did not) - a fragile inference over two
    unrelated fields that also requires knowing this coordinator's own
    internal gating order. The target symbol itself is deliberately not
    duplicated here: the caller already supplied it via ``context.symbol``
    on their own call to ``run_runtime_cycle``, so there is exactly one
    target symbol this fact could possibly refer to - no ambiguity to
    resolve by re-exposing it.
    """

    as_of: Timestamp
    outcome: RuntimeCycleOutcome
    mt5_runtime_status: MT5RuntimeStatus
    account_facts: MT5AccountFacts | None = None
    account_position_mode: AccountPositionMode | None = None
    positions_read_status: PositionsReadStatus | None = None
    history_read_status: HistoryReadStatus | None = None
    target_symbol_facts_available: bool | None = None
    rollover_snapshot: MT5RolloverSnapshot | None = None
    rollover_persisted: bool | None = None
    realized_daily_pnl_assessment: MT5RealizedDailyPnLAssessment | None = None
    open_risk_assessment: MT5OpenRiskAssessment | None = None
    account_risk_snapshot_assembly: AccountRiskSnapshotAssembly | None = None
    decision_risk_pipeline_result: DecisionRiskPipelineResult | None = None
    final_recommendation_construction_result: FinalRecommendationConstructionResult | None = None
    netting_guard_result: NettingGuardResult | None = None
    new_tracking_results: tuple[TrackedRecommendationConstructionResult, ...] = ()
    new_tracking_persistence_outcomes: tuple[TrackingIssuancePersistenceOutcome, ...] = ()
    advanced_tracking: tuple[AdvancedTrackedRecommendationOutcome, ...] = ()
    excluded_tracked_recommendations: tuple[ExcludedTrackedRecommendation, ...] = ()


__all__ = [
    "AdvancedTrackedRecommendationOutcome",
    "ExcludedTrackedRecommendation",
    "HistoryReadStatus",
    "NettingGuardResult",
    "PositionsReadStatus",
    "RuntimeCycleResult",
    "TrackingIssuancePersistenceOutcome",
]
