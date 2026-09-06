"""LLM Explanation Layer - deterministic fallback tests (NEXT STAGE, Core).

Every test here exercises ``render_deterministic_fallback`` with no LLM
client involved at all, and - per the corrected architectural boundary -
with no ``RuntimeCycleResult`` passed to it either: the fallback works
purely from an already-built ``ExplanationContext`` and the already-built
authoritative cards.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.core.enums.explanation import ExplanationContentStatus, ExplanationProviderStatus
from app.core.enums.mt5_runtime import AccountPositionMode
from app.core.enums.runtime_cycle import NettingIssuanceOutcome
from app.core.models.runtime_cycle import RuntimeCycleResult
from app.orchestration.explanation import (
    build_explanation_context,
    build_recommendation_cards,
    build_tracking_cards,
    render_deterministic_fallback,
)
from tests.explanation_support import (
    blocked_result,
    degraded_issuance_suppressed_result,
    degraded_with_recommendation_present_result,
    netting_existing_broker_position_blocked_result,
    netting_existing_unresolved_blocked_result,
    netting_multiple_actionable_blocked_result,
    ready_actionable_hedging_result,
    ready_no_actionable_result,
    tracking_lifecycle_result,
    unknown_mode_multiple_actionable_blocked_result,
    unknown_mode_result,
)


def _fallback(result, provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE):
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)
    return render_deterministic_fallback(
        context=context, recommendation_cards=cards, tracking_cards=tracking, provider_status=provider_status
    )


# --- A: fallback function has no RuntimeCycleResult parameter ---


def test_fallback_signature_has_no_runtime_cycle_result_parameter() -> None:
    signature = inspect.signature(render_deterministic_fallback, eval_str=True)
    assert set(signature.parameters) == {"context", "recommendation_cards", "tracking_cards", "provider_status"}
    assert "result" not in signature.parameters
    for parameter in signature.parameters.values():
        assert parameter.annotation is not RuntimeCycleResult


# --- B: fallback works entirely from ExplanationContext + cards ---


def test_fallback_works_entirely_from_context_and_cards_no_result_needed(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    cards = build_recommendation_cards(result)
    tracking = build_tracking_cards(result)

    # constructed and called with no reference to `result` at all beyond
    # having built context/cards from it earlier - proves the fallback call
    # itself needs nothing more:
    outcome = render_deterministic_fallback(
        context=context, recommendation_cards=cards, tracking_cards=tracking, provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE
    )
    assert outcome.recommendation_cards == cards
    assert len(outcome.recommendation_explanations) == 1


# --- X: deterministic fallback actionable ---


def test_fallback_actionable_recommendation(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    fallback = _fallback(result)

    assert fallback.content_status is ExplanationContentStatus.AVAILABLE
    assert len(fallback.recommendation_cards) == 1
    assert len(fallback.recommendation_explanations) == 1
    card = fallback.recommendation_cards[0]
    narrative = fallback.recommendation_explanations[0].narrative
    assert card.trade_id in {e.trade_id for e in fallback.recommendation_explanations}
    assert card.symbol in narrative
    assert card.direction.value in narrative
    assert str(card.entry_price) in narrative or format(card.entry_price, "f") in narrative
    assert fallback.no_trade_explanation is None


# --- Y: deterministic fallback no-trade (business no-trade) ---


def test_fallback_business_no_trade(tmp_path: Path) -> None:
    result = ready_no_actionable_result(tmp_path)
    fallback = _fallback(result)

    assert fallback.recommendation_cards == ()
    assert fallback.recommendation_explanations == ()
    assert fallback.no_trade_explanation is not None
    assert "NO_ACTIONABLE_FAMILY" in fallback.no_trade_explanation
    assert "Runtime cycle blocked" not in fallback.headline


# --- Z: deterministic fallback degraded (both shapes) ---


def test_fallback_degraded_with_recommendation_present(tmp_path: Path) -> None:
    result = degraded_with_recommendation_present_result(tmp_path)
    fallback = _fallback(result)

    assert result.outcome.value == "PARTIAL_DEGRADED"
    assert len(fallback.recommendation_cards) == 1  # useful work preserved
    assert any("bad" in w for w in fallback.warnings)


def test_fallback_degraded_issuance_suppressed(tmp_path: Path) -> None:
    result = degraded_issuance_suppressed_result(tmp_path)
    fallback = _fallback(result)

    assert result.outcome.value == "PARTIAL_DEGRADED"
    assert fallback.recommendation_cards == ()
    assert any("open-position read was unavailable" in w for w in fallback.warnings)
    # existing tracking still advanced, must remain visible:
    assert len(fallback.tracking_cards) == 1


# --- AA: deterministic fallback BLOCKED ---


def test_fallback_blocked_runtime(tmp_path: Path) -> None:
    result = blocked_result(tmp_path)
    fallback = _fallback(result)

    assert fallback.content_status is ExplanationContentStatus.AVAILABLE
    assert fallback.recommendation_cards == ()
    assert fallback.no_trade_explanation is None
    assert "blocked" in fallback.headline.lower()
    assert "INITIALIZATION_FAILED" in fallback.cycle_summary


def test_fallback_blocked_distinguishable_from_no_trade(tmp_path: Path) -> None:
    """The explanation must clearly distinguish business no-trade from
    technical/runtime inability to complete the cycle."""
    blocked = _fallback(blocked_result(tmp_path / "blocked"))
    no_trade = _fallback(ready_no_actionable_result(tmp_path / "no_trade"))
    assert blocked.headline != no_trade.headline
    assert blocked.cycle_summary != no_trade.cycle_summary


# --- M: each NETTING block reason ---


def test_fallback_netting_existing_broker_position(tmp_path: Path) -> None:
    result = netting_existing_broker_position_blocked_result(tmp_path)
    fallback = _fallback(result)
    assert any("existing broker position" in w for w in fallback.warnings)
    assert not any("strategy" in w.lower() and "reject" in w.lower() for w in fallback.warnings)


def test_fallback_netting_existing_unresolved_recommendation(tmp_path: Path) -> None:
    result = netting_existing_unresolved_blocked_result(tmp_path)
    fallback = _fallback(result)
    assert any("still pending or open" in w for w in fallback.warnings)


def test_fallback_netting_multiple_actionable(tmp_path: Path) -> None:
    result = netting_multiple_actionable_blocked_result(tmp_path)
    fallback = _fallback(result)
    assert any("multiple strategies qualified" in w for w in fallback.warnings)
    # both recommendations are still real, authoritative facts from the
    # deterministic engine (Final Recommendation construction has no notion
    # of the Part-F netting guard) - they are shown, unranked, with no
    # tracking creation attempted for either (issuance was withheld):
    assert len(fallback.recommendation_cards) == 2
    assert all(card.tracking_creation_outcome is None for card in fallback.recommendation_cards)


# --- N: UNKNOWN fail-closed wording ---


def test_fallback_unknown_mode_allowed_when_safe_invariant_satisfied(tmp_path: Path) -> None:
    """UNKNOWN + flat/uncontested/single-actionable -> genuinely ALLOWED,
    exactly like a safe NETTING cycle would be - confirms UNKNOWN is never
    treated as an automatic block."""
    result = unknown_mode_result(tmp_path)
    assert result.account_position_mode is AccountPositionMode.UNKNOWN
    assert result.netting_guard_result.account_position_mode is AccountPositionMode.UNKNOWN
    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.ALLOWED


def test_fallback_unknown_mode_blocked_uses_conservative_wording_never_hedging_never_strategy_rejection(
    tmp_path: Path,
) -> None:
    """UNKNOWN + multiple actionable FinalRecommendations -> genuinely
    BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS under UNKNOWN's own
    conservative fail-closed handling (never NETTING's, never HEDGING's).
    Proves the fallback's UNKNOWN mode-note branch is actually exercised and
    worded correctly, and that both authoritative recommendation cards
    remain visible and unranked while issuance is withheld for the guarded
    symbol."""
    result = unknown_mode_multiple_actionable_blocked_result(tmp_path)

    assert result.account_position_mode is AccountPositionMode.UNKNOWN
    assert result.netting_guard_result is not None
    assert result.netting_guard_result.account_position_mode is AccountPositionMode.UNKNOWN
    assert result.netting_guard_result.outcome is NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS

    fallback = _fallback(result)

    conservative_warning = next(
        (
            w
            for w in fallback.warnings
            if "position-netting mode could not be determined" in w and "conservative" in w.lower() and "restrictions were applied" in w
        ),
        None,
    )
    assert conservative_warning is not None, f"no conservative UNKNOWN wording found in warnings: {fallback.warnings}"

    combined = " ".join(fallback.warnings).lower()
    assert "hedging" not in combined
    assert "strategy rejection" not in combined
    assert "reject" not in combined

    # both deterministic recommendations remain visible and unranked while
    # issuance/tracking is withheld for the guarded symbol:
    assert len(fallback.recommendation_cards) == 2
    assert all(card.tracking_creation_outcome is None for card in fallback.recommendation_cards)
    assert {card.trade_id for card in fallback.recommendation_cards} == {"trade-long", "trade-short"}


# --- O: each tracking lifecycle status ---


def test_fallback_tracking_pending(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "PENDING")
    fallback = _fallback(result)
    assert "awaiting broker fill confirmation" in fallback.tracking_explanations[0].narrative


def test_fallback_tracking_open(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "OPEN")
    fallback = _fallback(result)
    assert "currently open" in fallback.tracking_explanations[0].narrative


def test_fallback_tracking_win(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "WIN")
    fallback = _fallback(result)
    narrative = fallback.tracking_explanations[0].narrative
    assert "profit" in narrative
    assert "50" in narrative


def test_fallback_tracking_loss(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "LOSS")
    fallback = _fallback(result)
    narrative = fallback.tracking_explanations[0].narrative
    assert "loss" in narrative
    assert "-50" in narrative


def test_fallback_tracking_breakeven(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "BREAKEVEN")
    fallback = _fallback(result)
    assert "breakeven" in fallback.tracking_explanations[0].narrative


def test_fallback_tracking_not_filled(tmp_path: Path) -> None:
    result = tracking_lifecycle_result(tmp_path, "NOT_FILLED")
    fallback = _fallback(result)
    assert "without a confirmed fill" in fallback.tracking_explanations[0].narrative


def test_fallback_never_predicts_or_recalculates(tmp_path: Path) -> None:
    """No causal invention: fallback text for a lifecycle status only ever
    restates the already-known status/PnL, never a forecast."""
    result = tracking_lifecycle_result(tmp_path, "OPEN")
    fallback = _fallback(result)
    narrative = fallback.tracking_explanations[0].narrative.lower()
    for forbidden in ("expect", "predict", "likely", "forecast", "will probably"):
        assert forbidden not in narrative


# --- provider_status passthrough ---


def test_fallback_reports_caller_supplied_provider_status(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    fallback = _fallback(result, provider_status=ExplanationProviderStatus.LLM_INVALID_OUTPUT)
    assert fallback.provider_status is ExplanationProviderStatus.LLM_INVALID_OUTPUT
    assert fallback.content_status is ExplanationContentStatus.AVAILABLE
