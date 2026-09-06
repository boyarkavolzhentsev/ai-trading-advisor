"""Final Recommendation -> Stage 10E tracking-creation integration (Final
Runtime Integration, Part E).

Converts one already-completed ``FinalRecommendationConstructionResult`` into
one Stage 10E ``MT5TrackedRecommendationCreationResult`` (via the existing,
unmodified ``app.mt5.tracker.create_tracked_recommendation``) plus one
durable ``FinalRecommendationProvenance`` (see the approved Part E
corrective design), per ACTIONABLE family - independently, never
ranking/selecting/collapsing/reconciling across families.

Never invokes ``MT5Client``/``MetaTrader5``, ``app.mt5.matching``,
``app.mt5.history``, either persistence module
(``app.mt5.recommendation_persistence``/``app.mt5.
recommendation_provenance_persistence``), never constructs/writes either
persisted document, and never reads the filesystem, the network, or the wall
clock - a pure, synchronous, stateless function of its five explicit inputs
only. The caller-confirmed ``pre_existing_positions_read_status``/
``pre_existing_positions`` snapshot is passed unchanged to every
``create_tracked_recommendation`` call this cycle: this module never reads
MT5 positions itself, and never fabricates a snapshot (see the approved
snapshot read-once/thread-many architecture - the future runtime-cycle
orchestrator, not yet built, owns the single ``positions()`` read).

``market: MarketType`` is caller/runtime-owned and explicit - never inferred
from ``symbol``, never derived from any ``ContractType`` - and is applied
unchanged to every family this cycle: one ``FinalRecommendationConstructionResult``
carries exactly one symbol, hence exactly one market, by construction (see
``app.orchestration.final_recommendation``).
"""

from __future__ import annotations

from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.market import MarketType
from app.core.models.base import Timestamp
from app.core.models.final_recommendation import FinalRecommendationConstructionResult
from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance
from app.core.models.mt5_position import MT5Position
from app.core.models.tracking_integration import TrackedRecommendationConstructionResult
from app.mt5.risk import MT5PositionsReadStatus
from app.mt5.tracker import create_tracked_recommendation


def construct_tracked_recommendations(
    *,
    final_recommendation_construction_result: FinalRecommendationConstructionResult,
    as_of: Timestamp,
    market: MarketType,
    pre_existing_positions_read_status: MT5PositionsReadStatus,
    pre_existing_positions: tuple[MT5Position, ...],
) -> tuple[TrackedRecommendationConstructionResult, ...]:
    """Process every ACTIONABLE family independently, in
    ``final_recommendation_construction_result.family_results`` order -
    Stage 9's own deterministic family order, unchanged. Zero ACTIONABLE
    families yields an empty tuple, never a fabricated placeholder result.
    """
    results: list[TrackedRecommendationConstructionResult] = []

    for family_result in final_recommendation_construction_result.family_results:
        if family_result.verdict is not FinalRecommendationVerdict.ACTIONABLE:
            continue

        recommendation = family_result.recommendation
        assert recommendation is not None  # guaranteed by ACTIONABLE

        tracking_creation_result = create_tracked_recommendation(
            as_of=as_of,
            trade_id=recommendation.trade_id,
            symbol=recommendation.symbol,
            market=market,
            direction=recommendation.direction,
            signal_time=recommendation.signal_time,
            valid_until=recommendation.valid_until,
            planned_entry=recommendation.entry_price,
            stop_loss=recommendation.stop_loss,
            take_profit_levels=recommendation.take_profit_levels,
            approved_broker_volume=recommendation.approved_volume,
            pre_existing_positions_read_status=pre_existing_positions_read_status,
            pre_existing_positions=pre_existing_positions,
        )
        provenance = FinalRecommendationProvenance(
            trade_id=recommendation.trade_id,
            family=recommendation.family,
            approved_risk_amount=recommendation.approved_risk_amount,
            account_currency=recommendation.account_currency,
        )
        results.append(
            TrackedRecommendationConstructionResult(
                trade_id=recommendation.trade_id,
                tracking_creation_result=tracking_creation_result,
                provenance=provenance,
            )
        )

    return tuple(results)


__all__ = ["construct_tracked_recommendations"]
