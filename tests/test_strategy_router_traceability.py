"""Stage 6A embeds the supplied ``MarketEvaluationResult`` unchanged - no
evidence, observation, or provenance is copied out of it."""

from __future__ import annotations

from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult
from app.strategies.router import StrategyRouter
from tests.market_evaluation_support import full_external_result, full_flow_result, full_technical_result, make_context
from tests.strategy_router_support import evaluation


def test_market_evaluation_embedded_unchanged() -> None:
    market_evaluation = evaluation(
        technical=full_technical_result(), flow=full_flow_result(), external=full_external_result(), context=make_context()
    )
    result = StrategyRouter().route(market_evaluation=market_evaluation)
    assert result.market_evaluation == market_evaluation
    assert result.market_evaluation.flow == market_evaluation.flow
    assert result.market_evaluation.technical == market_evaluation.technical
    assert result.market_evaluation.external == market_evaluation.external


def test_no_evidence_shaped_field_on_new_models() -> None:
    forbidden = {"evidence", "observations", "provenance", "analyst_results", "scope_summaries"}
    assert forbidden.isdisjoint(StrategyEligibilityEntry.model_fields)
    assert forbidden.isdisjoint(StrategyRouterResult.model_fields)


def test_router_result_field_set_is_exactly_the_approved_contract() -> None:
    assert set(StrategyRouterResult.model_fields) == {
        "market_evaluation",
        "outcome",
        "eligibility",
        "eligible_families",
    }
    assert set(StrategyEligibilityEntry.model_fields) == {"family", "eligible", "ineligibility_reasons"}
