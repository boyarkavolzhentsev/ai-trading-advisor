"""LLM Explanation Layer - orchestration/validation/retry tests (NEXT STAGE,
Core)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.enums.explanation import ExplanationContentStatus, ExplanationProviderStatus
from app.core.models.explanation import (
    ExplanationLLMResponse,
    ExplanationNarrative,
    RecommendationExplanation,
    TrackingExplanation,
)
from app.orchestration.explanation import (
    build_explanation_context,
    build_recommendation_cards,
    build_tracking_cards,
    explain_runtime_cycle,
)
from tests.explanation_support import FakeExplanationLLMClient, ready_actionable_hedging_result


def _valid_narrative_for(context, recommendation_cards, tracking_cards) -> ExplanationNarrative:
    recommendation_explanations = tuple(
        RecommendationExplanation(
            trade_id=card.trade_id,
            family=card.family,
            narrative=f"{card.family.value} recommendation on {card.symbol}.",
            cited_fact_ids=(f"recommendation.{card.trade_id}.entry_price",),
        )
        for card in recommendation_cards
    )
    tracking_explanations = tuple(
        TrackingExplanation(
            trade_id=card.trade_id,
            narrative=f"{card.symbol} tracking update.",
            cited_fact_ids=(f"tracking.{card.trade_id}.status",),
        )
        for card in tracking_cards
    )
    return ExplanationNarrative(
        headline="Cycle explained",
        cycle_summary="Everything ran as expected.",
        recommendation_explanations=recommendation_explanations,
        tracking_explanations=tracking_explanations,
    )


# --- F: actionable recommendation explanation (valid LLM path) ---


def test_actionable_recommendation_explained_by_llm(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=narrative)])

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert outcome.content_status is ExplanationContentStatus.AVAILABLE
    assert outcome.provider_status is ExplanationProviderStatus.LLM_SUCCESS
    assert outcome.recommendation_cards == cards
    assert outcome.recommendation_explanations == narrative.recommendation_explanations
    assert len(client.calls) == 1


# --- P/Q: cited_fact_id validation ---


def test_valid_cited_fact_ids_accepted(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=narrative)])

    outcome = explain_runtime_cycle(result=result, llm_client=client)
    assert outcome.provider_status is ExplanationProviderStatus.LLM_SUCCESS


def test_unknown_fact_id_rejected_and_falls_back(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    bad_narrative = narrative.model_copy(
        update={
            "recommendation_explanations": (
                narrative.recommendation_explanations[0].model_copy(update={"cited_fact_ids": ("does.not.exist",)}),
            )
        }
    )
    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=bad_narrative), ExplanationLLMResponse(narrative=narrative)])

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert outcome.provider_status is ExplanationProviderStatus.LLM_SUCCESS  # succeeded on the one permitted retry
    assert len(client.calls) == 2
    assert client.calls[1].previous_validation_error is not None


# --- R: mismatched recommendation trade_id rejected ---


def test_mismatched_recommendation_trade_id_rejected(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    bad_narrative = narrative.model_copy(
        update={"recommendation_explanations": (narrative.recommendation_explanations[0].model_copy(update={"trade_id": "wrong-id"}),)}
    )
    client = FakeExplanationLLMClient(
        [ExplanationLLMResponse(narrative=bad_narrative), ExplanationLLMResponse(narrative=bad_narrative)]
    )

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert outcome.provider_status is ExplanationProviderStatus.LLM_INVALID_OUTPUT
    assert outcome.recommendation_cards == cards  # authoritative cards still present via fallback
    assert len(client.calls) == 2


# --- S: mismatched family rejected ---


def test_mismatched_family_rejected(tmp_path: Path) -> None:
    from app.core.enums.strategy_router import StrategyFamily

    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    wrong_family = StrategyFamily.BREAKOUT if cards[0].family is not StrategyFamily.BREAKOUT else StrategyFamily.MEAN_REVERSION
    bad_narrative = narrative.model_copy(
        update={"recommendation_explanations": (narrative.recommendation_explanations[0].model_copy(update={"family": wrong_family}),)}
    )
    client = FakeExplanationLLMClient(
        [ExplanationLLMResponse(narrative=bad_narrative), ExplanationLLMResponse(narrative=bad_narrative)]
    )

    outcome = explain_runtime_cycle(result=result, llm_client=client)
    assert outcome.provider_status is ExplanationProviderStatus.LLM_INVALID_OUTPUT


# --- T: mismatched tracking trade_id rejected ---


def test_mismatched_tracking_trade_id_rejected(tmp_path: Path) -> None:
    from tests.explanation_support import tracking_lifecycle_result

    result = tracking_lifecycle_result(tmp_path, "OPEN")
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    narrative = _valid_narrative_for(context, cards, tracking)
    bad_narrative = narrative.model_copy(
        update={"tracking_explanations": (narrative.tracking_explanations[0].model_copy(update={"trade_id": "wrong-id"}),)}
    )
    client = FakeExplanationLLMClient(
        [ExplanationLLMResponse(narrative=bad_narrative), ExplanationLLMResponse(narrative=bad_narrative)]
    )

    outcome = explain_runtime_cycle(result=result, llm_client=client)
    assert outcome.provider_status is ExplanationProviderStatus.LLM_INVALID_OUTPUT
    assert outcome.tracking_cards == tracking


# --- U: invalid schema -> exactly one retry ---


def test_invalid_first_response_retried_exactly_once_then_succeeds(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    valid = _valid_narrative_for(context, cards, tracking)

    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=None), ExplanationLLMResponse(narrative=valid)])
    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert len(client.calls) == 2
    assert outcome.provider_status is ExplanationProviderStatus.LLM_SUCCESS


# --- V: second invalid response -> deterministic fallback / LLM_INVALID_OUTPUT ---


def test_second_invalid_response_falls_back(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=None), ExplanationLLMResponse(narrative=None)])

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert len(client.calls) == 2  # no more than one retry - never infinite
    assert outcome.provider_status is ExplanationProviderStatus.LLM_INVALID_OUTPUT
    assert outcome.content_status is ExplanationContentStatus.AVAILABLE
    assert len(outcome.recommendation_cards) == 1  # deterministic recommendation never suppressed


# --- W: provider unavailable -> deterministic fallback / LLM_UNAVAILABLE, never retried ---


def test_provider_exception_falls_back_immediately_without_retry(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    client = FakeExplanationLLMClient([TimeoutError("provider timed out")])

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert len(client.calls) == 1  # exception is never retried
    assert outcome.provider_status is ExplanationProviderStatus.LLM_UNAVAILABLE
    assert outcome.content_status is ExplanationContentStatus.AVAILABLE
    assert len(outcome.recommendation_cards) == 1


def test_provider_exception_on_retry_attempt_never_happens_after_invalid_then_exception(tmp_path: Path) -> None:
    """Invalid output followed by a provider exception on the single retry:
    exactly two calls total, fallback used, LLM_UNAVAILABLE (the exception is
    the terminal signal)."""
    result = ready_actionable_hedging_result(tmp_path)
    client = FakeExplanationLLMClient([ExplanationLLMResponse(narrative=None), ConnectionError("down")])

    outcome = explain_runtime_cycle(result=result, llm_client=client)

    assert len(client.calls) == 2
    assert outcome.provider_status is ExplanationProviderStatus.LLM_UNAVAILABLE


# --- AC: RuntimeCycleResult unchanged after explanation ---


def test_runtime_cycle_result_never_mutated(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    snapshot = result.model_copy(deep=True)

    client = FakeExplanationLLMClient([TimeoutError("boom")])
    explain_runtime_cycle(result=result, llm_client=client)

    assert result == snapshot


def test_runtime_cycle_result_unchanged_across_llm_success_invalid_and_unavailable(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    snapshot = result.model_copy(deep=True)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    valid = _valid_narrative_for(context, cards, tracking)

    for client in (
        FakeExplanationLLMClient([ExplanationLLMResponse(narrative=valid)]),
        FakeExplanationLLMClient([ExplanationLLMResponse(narrative=None), ExplanationLLMResponse(narrative=None)]),
        FakeExplanationLLMClient([RuntimeError("boom")]),
    ):
        explain_runtime_cycle(result=result, llm_client=client)
        assert result == snapshot
