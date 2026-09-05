"""Final Recommendation (Final Runtime Integration, Part D).

Converts one already-completed ``DecisionRiskPipelineResult`` into a per-
Session-eligible-``StrategyFamily`` broker-normalized, advisory-only
recommendation, joining Setup Construction's ``CandidateTradeSetup`` and
Stage 9's ``SessionFamilyResult`` by explicit ``StrategyFamily`` identity -
never by tuple position - then sizing each through the existing, unmodified
Stage 10C ``compute_broker_sizing``. Never reproduces any stage's own
business logic: tick-size/tick-value/risk-per-volume math, broker volume
min/max/step normalization, and risk-verification all remain Stage 10C's
exclusive authority.

Never invokes ``MT5Client``, ``account_info``/``symbol_info``/``positions``/
history/deals, any Stage 10E module (``app.mt5.matching``/``app.mt5.tracker``/
``app.mt5.recommendation_persistence``), and never constructs a
``PositionRecord`` - this stage only prepares a deterministic recommendation
object a later, not-yet-built integration block can hand to Stage 10E. Never
reads the filesystem, the network, or the wall clock - a pure, synchronous,
stateless function of its five explicit inputs only.

Account currency is never hardcoded, inferred, or converted: the caller
supplies ``account_currency`` directly from the already-existing, unmodified
``MT5AccountFacts.currency`` - no Stage 10A/B/7 contract is extended to carry
it, mirroring exactly how ``symbol_facts``/``m15_market_structure`` are
already supplied directly to Setup Construction rather than threaded through
the Decision/Risk Pipeline chain. No FX rate is ever fetched or computed.

``trade_ids`` is inert, caller-supplied data only: this module never
generates an identity (no wall clock, no counter, no persistence read, no
randomness of any kind). The coarse market-domain classifier
``PositionRecord`` will eventually need is deliberately never referenced
here at all - it belongs only to the later Final Recommendation -> Stage 10E
wiring boundary, which this stage does not build.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.final_recommendation import (
    FinalRecommendationBlockReason,
    FinalRecommendationOutcome,
    FinalRecommendationVerdict,
)
from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.session_gate import SessionFamilyVerdict
from app.core.enums.setup_construction import SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import Timestamp
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.final_recommendation import (
    FinalRecommendation,
    FinalRecommendationConstructionResult,
    FinalRecommendationFamilyResult,
)
from app.core.models.mt5_sizing import MT5BrokerSizingRequest
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.core.models.session_result import SessionFamilyResult
from app.core.models.setup_construction import SetupConstructionResult
from app.mt5.sizing import compute_broker_sizing
from app.orchestration.errors import MissingTradeIdForActionableFamilyError


def _blocked(
    family: StrategyFamily,
    reason: FinalRecommendationBlockReason,
    *,
    sizing_result=None,
) -> FinalRecommendationFamilyResult:
    return FinalRecommendationFamilyResult(
        family=family,
        verdict=FinalRecommendationVerdict.BLOCKED,
        reasons=(reason,),
        sizing_result=sizing_result,
    )


def _evaluate_family(
    *,
    session_result: SessionFamilyResult,
    setup_by_family: dict[StrategyFamily, SetupConstructionResult],
    symbol_facts: MT5SymbolFacts,
    account_currency: str,
    trade_ids: Mapping[StrategyFamily, str],
    as_of: Timestamp,
) -> FinalRecommendationFamilyResult:
    family = session_result.family

    if session_result.verdict is not SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW:
        return _blocked(family, FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE)

    setup_result = setup_by_family.get(family)
    assert setup_result is not None  # guaranteed: Session-eligible implies Risk-eligible implies CONSTRUCTED
    assert setup_result.outcome is SetupConstructionOutcome.CONSTRUCTED
    setup = setup_result.setup
    assert setup is not None

    if setup.symbol != symbol_facts.symbol:
        return _blocked(family, FinalRecommendationBlockReason.SYMBOL_FACTS_MISMATCH)

    if as_of > setup.valid_until:
        return _blocked(family, FinalRecommendationBlockReason.SETUP_EXPIRED)

    request = MT5BrokerSizingRequest(
        symbol=setup.symbol,
        direction=setup.direction,
        stop_loss=setup.stop_loss,
        entry_price=setup.entry_price,
        session_allocated_risk=session_result.session_allocated_risk,
    )
    sizing_result = compute_broker_sizing(as_of=as_of, request=request, symbol_facts=symbol_facts)

    if sizing_result.outcome is not MT5SizingOutcome.ACTIONABLE:
        return _blocked(family, FinalRecommendationBlockReason.SIZING_NOT_ACTIONABLE, sizing_result=sizing_result)

    trade_id = trade_ids.get(family)
    if trade_id is None:
        raise MissingTradeIdForActionableFamilyError(f"no trade_id supplied for actionable family {family}")

    assert sizing_result.broker_volume is not None  # guaranteed by ACTIONABLE
    assert sizing_result.actual_monetary_risk is not None  # guaranteed by ACTIONABLE

    recommendation = FinalRecommendation(
        trade_id=trade_id,
        family=family,
        symbol=setup.symbol,
        direction=setup.direction,
        entry_price=setup.entry_price,
        stop_loss=setup.stop_loss,
        take_profit_levels=setup.take_profit_levels,
        approved_volume=sizing_result.broker_volume,
        approved_risk_amount=sizing_result.actual_monetary_risk,
        account_currency=account_currency,
        signal_time=setup.signal_time,
        valid_until=setup.valid_until,
    )
    return FinalRecommendationFamilyResult(
        family=family,
        verdict=FinalRecommendationVerdict.ACTIONABLE,
        sizing_result=sizing_result,
        recommendation=recommendation,
    )


def construct_final_recommendations(
    *,
    decision_risk_pipeline_result: DecisionRiskPipelineResult,
    symbol_facts: MT5SymbolFacts,
    account_currency: str,
    trade_ids: Mapping[StrategyFamily, str],
    as_of: Timestamp,
) -> FinalRecommendationConstructionResult:
    """Construct one Final Recommendation per Session-eligible family.

    ``trade_ids`` need only cover the families the caller already knows are
    ``SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW`` on
    ``decision_risk_pipeline_result`` - never every ``StrategyFamily``
    unconditionally. A family that reaches sizing without a supplied
    ``trade_id`` raises ``MissingTradeIdForActionableFamilyError``: a
    caller-contract violation, never a business block reason.
    """
    if decision_risk_pipeline_result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK:
        return FinalRecommendationConstructionResult(
            decision_risk_pipeline_result=decision_risk_pipeline_result,
            outcome=FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK,
            family_results=(),
        )

    strategy_session_result = decision_risk_pipeline_result.strategy_session_result
    assert strategy_session_result is not None  # guaranteed by DecisionRiskPipelineOutcome.COMPLETED

    setup_by_family = {
        result.family: result for result in decision_risk_pipeline_result.strategy_setup_result.family_results
    }

    family_results = tuple(
        _evaluate_family(
            session_result=session_result,
            setup_by_family=setup_by_family,
            symbol_facts=symbol_facts,
            account_currency=account_currency,
            trade_ids=trade_ids,
            as_of=as_of,
        )
        for session_result in strategy_session_result.family_results
    )

    any_actionable = any(result.verdict is FinalRecommendationVerdict.ACTIONABLE for result in family_results)
    outcome = (
        FinalRecommendationOutcome.SOME_ACTIONABLE if any_actionable else FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
    )

    return FinalRecommendationConstructionResult(
        decision_risk_pipeline_result=decision_risk_pipeline_result,
        outcome=outcome,
        family_results=family_results,
    )


__all__ = ["construct_final_recommendations"]
