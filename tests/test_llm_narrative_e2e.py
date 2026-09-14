"""Stage AI-D local fake end-to-end tests.

Proves a validated LLM narrative - and, on provider failure, the
deterministic fallback's own template narrative - reaches actual
Telegram-rendered text without ever being able to mutate an authoritative
trading fact. Every layer in the chain (``explain_runtime_cycle`` ->
``map_advisory_response`` -> ``render_advisory_response``) is the real,
unmocked production code; only the LLM provider boundary itself
(``ExplanationLLMClient.explain``) is faked. No ``openai`` SDK import, no
``httpx``/``requests``, no socket module anywhere in this file - the fakes
used are either plain local classes or the existing
``tests.explanation_support.FakeExplanationLLMClient``/
``tests.production_advisory_support.FakeFlowBootstrap`` fixtures, none of
which touch a network.
"""

from __future__ import annotations

from pathlib import Path

from app.application.advisory_service import map_advisory_response
from app.core.enums.explanation import ExplanationProviderStatus
from app.core.models.explanation import (
    ExplanationLLMResponse,
    ExplanationNarrative,
    ExplanationRequest,
    RecommendationExplanation,
    TrackingExplanation,
)
from app.orchestration.explanation import (
    build_explanation_context,
    build_recommendation_cards,
    build_tracking_cards,
    explain_runtime_cycle,
    render_deterministic_fallback,
)
from app.production_advisory.result import ProductionAdvisoryCycleOutcome, ProductionAdvisoryCycleResult
from app.telegram.rendering import pack_message_sections, render_advisory_response
from tests.explanation_support import FakeExplanationLLMClient, ready_actionable_hedging_result
from tests.production_advisory_support import FakeFlowBootstrap


class _CountingRaisingExplanationClient:
    """Local-only fake: raises on every call, counts how many were made.

    Deliberately not the shared ``tests.production_advisory_support.
    RaisingExplanationClient`` (which carries no call counter) - kept local
    to this module rather than widening that shared fixture's surface for a
    single test's own bookkeeping need."""

    def __init__(self) -> None:
        self.calls = 0

    def explain(self, request: ExplanationRequest) -> ExplanationLLMResponse:
        self.calls += 1
        raise RuntimeError("fake LLM provider unavailable")


def _cycle_result(runtime_cycle_result, explanation_result, *, llm_enabled: bool) -> ProductionAdvisoryCycleResult:
    return ProductionAdvisoryCycleResult(
        as_of=runtime_cycle_result.as_of,
        symbol="BTC",
        outcome=ProductionAdvisoryCycleOutcome.READY,
        runtime_cycle_result=runtime_cycle_result,
        explanation_result=explanation_result,
        llm_enabled=llm_enabled,
        flow_health=FakeFlowBootstrap().health(),
        technical_fetch_failures=(),
        cycle_duration_seconds=0.01,
    )


def test_llm_narrative_reaches_telegram_without_mutating_authoritative_facts(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    context = build_explanation_context(result)

    distinctive_marker = "distinctive-llm-narrative-marker-4f9a"
    recommendation_explanations = tuple(
        RecommendationExplanation(
            trade_id=card.trade_id,
            family=card.family,
            narrative=f"{distinctive_marker}: {card.family.value} recommendation on {card.symbol}.",
            cited_fact_ids=(f"recommendation.{card.trade_id}.entry_price",),
        )
        for card in cards
    )
    tracking_explanations = tuple(
        TrackingExplanation(trade_id=card.trade_id, narrative=f"{card.symbol} tracking update.")
        for card in tracking
    )
    narrative = ExplanationNarrative(
        headline="Cycle explained",
        cycle_summary="Everything ran as expected.",
        recommendation_explanations=recommendation_explanations,
        tracking_explanations=tracking_explanations,
    )
    fake_client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=narrative)])

    llm_explanation_result = explain_runtime_cycle(result=result, llm_client=fake_client)
    assert llm_explanation_result.provider_status is ExplanationProviderStatus.LLM_SUCCESS

    # Deterministic fallback of the SAME RuntimeCycleResult - the baseline
    # every authoritative field below is compared against.
    fallback_explanation_result = render_deterministic_fallback(
        context=context,
        recommendation_cards=cards,
        tracking_cards=tracking,
        provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
    )

    llm_response = map_advisory_response(
        logical_cycle_id="cyc-llm", cycle=_cycle_result(result, llm_explanation_result, llm_enabled=True)
    )
    fallback_response = map_advisory_response(
        logical_cycle_id="cyc-fallback", cycle=_cycle_result(result, fallback_explanation_result, llm_enabled=False)
    )

    full_text = "\n".join(render_advisory_response(llm_response))

    # A: distinctive LLM narrative appears in the real Telegram-rendered text.
    assert distinctive_marker in full_text
    assert "Explanation source: AI" in full_text

    # B: authoritative recommendation/status/no-trade-reason fields are
    # byte-identical to the deterministic-fallback run of the identical
    # RuntimeCycleResult - narrative source has zero effect on them.
    assert llm_response.recommendations == fallback_response.recommendations
    assert llm_response.status == fallback_response.status
    assert llm_response.no_trade_reasons == fallback_response.no_trade_reasons

    # C: explicit per-field checks that the LLM cannot mutate a trading fact.
    rec = llm_response.recommendations[0]
    original_card = cards[0]
    assert rec.direction == original_card.direction
    assert rec.symbol == original_card.symbol
    assert rec.entry_price == original_card.entry_price
    assert rec.stop_loss == original_card.stop_loss
    assert rec.approved_volume == original_card.approved_volume
    assert rec.approved_risk_amount == original_card.approved_risk_amount
    # no_trade_reasons for the OTHER (non-actionable) strategy families this
    # cycle are unaffected too - already proven equal to the fallback run
    # above; this fixture is not expected to produce zero of them.

    # D: exactly one LLM call on a valid first response - no retry needed.
    assert len(fake_client.calls) == 1

    # E: no external network call occurred, by construction - fake_client is
    # a plain local object (tests.explanation_support.FakeExplanationLLMClient)
    # with no openai/httpx/socket import anywhere in this module or that one.


def test_llm_provider_failure_falls_back_and_still_renders(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    cards = build_recommendation_cards(result)

    raising_client = _CountingRaisingExplanationClient()
    explanation_result = explain_runtime_cycle(result=result, llm_client=raising_client)  # must not raise
    assert explanation_result.provider_status is ExplanationProviderStatus.LLM_UNAVAILABLE

    response = map_advisory_response(
        logical_cycle_id="cyc-failure", cycle=_cycle_result(result, explanation_result, llm_enabled=True)
    )

    chunks = pack_message_sections(render_advisory_response(response))  # must not raise
    full_text = "".join(chunks)

    # deterministic fallback rendered, correctly labeled
    assert "Explanation source: deterministic" in full_text
    # the deterministic fallback's own fixed-template per-recommendation
    # narrative (see app.orchestration.explanation.render_deterministic_fallback)
    assert cards[0].trade_id in full_text
    assert f"approved risk" in full_text

    # authoritative recommendation fields unchanged despite the provider failure
    rec = response.recommendations[0]
    original_card = cards[0]
    assert rec.direction == original_card.direction
    assert rec.symbol == original_card.symbol
    assert rec.entry_price == original_card.entry_price
    assert rec.stop_loss == original_card.stop_loss
    assert rec.approved_volume == original_card.approved_volume
    assert rec.approved_risk_amount == original_card.approved_risk_amount

    # provider called exactly once - a raised exception is never retried
    assert raising_client.calls == 1

    # no external network call occurred, by construction - _CountingRaisingExplanationClient
    # is a plain local class with no openai/httpx/socket import anywhere in this file.
