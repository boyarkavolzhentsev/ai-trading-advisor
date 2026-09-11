"""``AdvisoryResponse``/``RecommendationDTO`` symbol semantics (corrective
design closure, "PROVIDER SYMBOL SPLIT + PRICE-BASIS RECONCILIATION"):

    AdvisoryResponse.symbol              = logical instrument   ("BTC")
    AdvisoryResponse.market_data_symbol  = Binance symbol        ("BTCUSDT")
    RecommendationDTO.symbol             = MT5 broker symbol     ("BTCUSDt")

Three genuinely distinct strings, proven never conflated.
"""

from __future__ import annotations

from app.application.advisory_service import map_advisory_response
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.application_support import (
    final_construction_result,
    final_family_result,
    netting_guard,
    one_family_actionable_others_ineligible,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)


def test_advisory_response_logical_and_market_data_symbols_are_independent_and_distinct() -> None:
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.READY)
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    # override the two cycle-level symbol facts directly, bypassing the
    # shared fixture's single-SYMBOL convenience default:
    cycle = cycle.model_copy(update={"symbol": "BTC", "market_data_symbol": "BTCUSDT"})

    response = map_advisory_response("cyc-1", cycle)

    assert response.symbol == "BTC"
    assert response.market_data_symbol == "BTCUSDT"
    assert response.symbol != response.market_data_symbol


def test_recommendation_dto_symbol_is_mt5_broker_symbol_independent_of_cycle_level_symbols() -> None:
    family = StrategyFamily.TREND_FOLLOWING
    trade_id = "cyc__TREND_FOLLOWING"
    mt5_symbol = "BTCUSDt"

    # build a real ACTIONABLE FinalRecommendation carrying the MT5 symbol -
    # distinct from both the logical ("BTC") and Binance ("BTCUSDT") cycle-
    # level symbols this same response will also carry.
    drp, _ = one_family_actionable_others_ineligible(family, trade_id)
    final_result = final_family_result(family, trade_id=trade_id)
    recommendation = final_result.recommendation.model_copy(update={"symbol": mt5_symbol})
    final_result = final_result.model_copy(update={"recommendation": recommendation})
    frcr = final_construction_result(drp, (final_result,))

    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=tracking,
    )
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    cycle = cycle.model_copy(update={"symbol": "BTC", "market_data_symbol": "BTCUSDT"})

    response = map_advisory_response("cyc-1", cycle)

    assert len(response.recommendations) == 1
    assert response.recommendations[0].symbol == mt5_symbol
    assert response.recommendations[0].symbol != response.symbol
    assert response.recommendations[0].symbol != response.market_data_symbol
