"""``app.telegram.rendering`` tests: READY/NO_TRADE/DEGRADED/
SERVICE_UNAVAILABLE rendering, Decimal precision, account currency, explicit
UTC, multi-recommendation ordering, and message-size packing."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.application.dto import ApplicationAdvisoryStatus, NoTradeReasonDTO, NoTradeStage
from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason
from app.telegram.rendering import (
    RenderingError,
    format_decimal,
    format_timestamp,
    pack_message_sections,
    render_advisory_response,
    render_no_trade_reason,
    split_narrative_text,
    render_recommendation,
)
from tests.telegram_support import build_advisory_response, build_recommendation


def test_format_decimal_preserves_exact_precision() -> None:
    assert format_decimal(Decimal("1.10000")) == "1.10000"
    assert format_decimal(Decimal("0.50")) == "0.50"
    assert format_decimal(Decimal("25.00")) == "25.00"


def test_format_decimal_never_goes_through_float() -> None:
    # Decimal("0.1") + Decimal("0.2") stays exact; float would show drift.
    value = Decimal("0.1") + Decimal("0.2")
    assert format_decimal(value) == "0.3"


def test_format_timestamp_utc_explicit() -> None:
    value = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    assert format_timestamp(value) == "2026-05-01T12:00:00+00:00"


def test_format_timestamp_non_utc_converted_to_utc() -> None:
    from datetime import timedelta, timezone

    eastern = timezone(timedelta(hours=-5))
    value = datetime(2026, 5, 1, 7, 0, 0, tzinfo=eastern)
    assert format_timestamp(value) == "2026-05-01T12:00:00+00:00"


def test_format_timestamp_naive_fails_closed() -> None:
    naive = datetime(2026, 5, 1, 12, 0, 0)
    with pytest.raises(RenderingError):
        format_timestamp(naive)


def test_render_recommendation_contains_all_authoritative_fields() -> None:
    rec = build_recommendation()
    text = render_recommendation(rec)
    assert rec.trade_id in text
    assert rec.symbol in text
    assert rec.strategy_family.value in text
    assert rec.direction.value in text
    assert "1.10000" in text
    assert "1.09000" in text
    assert "1.12000" in text
    assert "0.50" in text
    assert "25.00" in text
    assert rec.account_currency in text
    assert "2026-05-01" in text


def test_render_no_trade_reason_uses_raw_enum_values() -> None:
    reason = NoTradeReasonDTO(
        strategy_family=StrategyFamily.MEAN_REVERSION,
        stage=NoTradeStage.EVALUATION,
        codes=(StrategyIneligibilityReason.CONTOUR_MISSING,),
    )
    text = render_no_trade_reason(reason)
    assert "MEAN_REVERSION" in text
    assert "EVALUATION" in text
    assert "CONTOUR_MISSING" in text


def test_ready_rendering_single_recommendation() -> None:
    rec = build_recommendation()
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,))
    sections = render_advisory_response(response)
    joined = "\n".join(sections)
    assert "READY" in joined
    assert rec.trade_id in joined
    assert "NO TRADE" not in joined


def test_no_trade_rendering() -> None:
    reason = NoTradeReasonDTO(strategy_family=StrategyFamily.BREAKOUT, stage=NoTradeStage.SETUP, codes=(StrategyIneligibilityReason.CONTOUR_MISSING,))
    response = build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE, no_trade_reasons=(reason,))
    sections = render_advisory_response(response)
    joined = "\n".join(sections)
    assert "NO TRADE" in joined
    assert "BREAKOUT" in joined
    assert "SETUP" in joined


def test_degraded_rendering_shows_recommendation_and_marker() -> None:
    from app.core.enums.runtime_cycle import RuntimeCycleOutcome

    rec = build_recommendation()
    response = build_advisory_response(
        status=ApplicationAdvisoryStatus.DEGRADED, recommendations=(rec,), runtime_outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED
    )
    sections = render_advisory_response(response)
    joined = "\n".join(sections)
    assert "DEGRADED" in joined
    assert rec.trade_id in joined  # recommendation geometry never hidden because of DEGRADED
    assert "Diagnostics:" in joined


def test_service_unavailable_rendering_has_no_recommendation() -> None:
    response = build_advisory_response(status=ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE)
    sections = render_advisory_response(response)
    joined = "\n".join(sections)
    assert "SERVICE UNAVAILABLE" in joined
    assert "Trade:" not in joined


def test_multiple_recommendations_all_rendered_in_order() -> None:
    rec_1 = build_recommendation(trade_id="cyc__TREND_FOLLOWING")
    rec_2 = build_recommendation(trade_id="cyc__BREAKOUT")
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec_1, rec_2))
    sections = render_advisory_response(response)
    joined = "\n".join(sections)
    first_index = joined.index("cyc__TREND_FOLLOWING")
    second_index = joined.index("cyc__BREAKOUT")
    assert first_index < second_index


def test_zero_recommendations_renders_no_trade_marker() -> None:
    response = build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE, recommendations=())
    sections = render_advisory_response(response)
    assert any("NO TRADE" in section for section in sections)


# --- message packing ---------------------------------------------------


def test_pack_message_sections_single_chunk_when_small() -> None:
    chunks = pack_message_sections(["a", "b", "c"])
    assert len(chunks) == 1
    assert chunks[0] == "a\n\nb\n\nc"


def test_pack_message_sections_splits_when_exceeding_limit() -> None:
    sections = ["x" * 2000, "y" * 2000, "z" * 2000]
    chunks = pack_message_sections(sections, max_chunk_size=4000)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 4000
    # section order preserved across chunks, none dropped
    full_text = "".join(chunks)
    assert "x" * 2000 in full_text
    assert "y" * 2000 in full_text
    assert "z" * 2000 in full_text


def test_pack_message_sections_never_splits_a_single_section() -> None:
    sections = ["header", "x" * 3999]
    chunks = pack_message_sections(sections, max_chunk_size=4000)
    assert any("x" * 3999 == chunk or chunk.endswith("x" * 3999) for chunk in chunks)


def test_pack_message_sections_raises_on_oversized_atomic_section() -> None:
    with pytest.raises(RenderingError):
        pack_message_sections(["x" * 5000], max_chunk_size=4000)


def test_many_no_trade_reasons_produce_multiple_chunks_no_loss() -> None:
    reasons = tuple(
        NoTradeReasonDTO(strategy_family=StrategyFamily.BREAKOUT, stage=NoTradeStage.EVALUATION, codes=(StrategyIneligibilityReason.CONTOUR_MISSING,))
        for _ in range(400)
    )
    response = build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE, no_trade_reasons=reasons)
    sections = render_advisory_response(response)
    chunks = pack_message_sections(sections)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4000
    # every reason line must appear somewhere across the chunks (nothing dropped)
    full_text = "\n".join(chunks)
    assert full_text.count("BREAKOUT") == 400


# --- pre-commit rendering-safety review: narrative must never suppress ----
# --- an already-approved recommendation ------------------------------------


def test_split_narrative_text_preserves_full_content_and_order() -> None:
    text = "abc" * 2000  # 6000 chars
    pieces = split_narrative_text(text, max_size=4000)
    assert len(pieces) == 2
    assert all(len(piece) <= 4000 for piece in pieces)
    assert "".join(pieces) == text  # concatenation reproduces the original exactly


def test_split_narrative_text_short_text_single_piece() -> None:
    assert split_narrative_text("short") == ["short"]


def test_split_narrative_text_empty_text_no_pieces() -> None:
    assert split_narrative_text("") == []


def test_ready_recommendation_survives_huge_cycle_summary() -> None:
    """The exact bug this review found: a 10,000-character cycle_summary
    must never cause RenderingError, and the recommendation must still be
    delivered - never silently replaced by an internal-error fallback."""
    rec = build_recommendation()
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,))
    response = response.model_copy(update={"explanation": response.explanation.model_copy(update={"cycle_summary": "x" * 10_000})})

    sections = render_advisory_response(response)  # must not raise
    chunks = pack_message_sections(sections)  # must not raise

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4000
    full_text = "".join(chunks)
    assert rec.trade_id in full_text
    assert full_text.count("x") >= 10_000  # narrative fully preserved, nothing dropped


def test_ready_recommendation_chunk_precedes_narrative_chunks() -> None:
    rec = build_recommendation()
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,))
    response = response.model_copy(update={"explanation": response.explanation.model_copy(update={"cycle_summary": "n" * 10_000})})

    chunks = pack_message_sections(render_advisory_response(response))
    recommendation_chunk_index = next(i for i, chunk in enumerate(chunks) if rec.trade_id in chunk)
    narrative_chunk_indexes = [i for i, chunk in enumerate(chunks) if "n" * 100 in chunk]
    assert narrative_chunk_indexes  # sanity: narrative did produce chunks
    assert recommendation_chunk_index < min(narrative_chunk_indexes)


def test_degraded_recommendation_survives_huge_warning() -> None:
    from app.core.enums.runtime_cycle import RuntimeCycleOutcome

    rec = build_recommendation()
    response = build_advisory_response(
        status=ApplicationAdvisoryStatus.DEGRADED, recommendations=(rec,), runtime_outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED
    )
    response = response.model_copy(update={"explanation": response.explanation.model_copy(update={"warnings": ("w" * 8_000,)})})

    chunks = pack_message_sections(render_advisory_response(response))  # must not raise
    full_text = "".join(chunks)
    assert rec.trade_id in full_text
    assert "DEGRADED" in full_text
    recommendation_chunk_index = next(i for i, chunk in enumerate(chunks) if rec.trade_id in chunk)
    narrative_chunk_indexes = [i for i, chunk in enumerate(chunks) if "w" * 100 in chunk]
    assert narrative_chunk_indexes
    assert recommendation_chunk_index < min(narrative_chunk_indexes)


def test_oversized_authoritative_recommendation_block_still_raises() -> None:
    """Authoritative recommendation blocks remain atomic - an oversized one
    must still fail loudly, never be silently truncated. trade_id has no
    max_length constraint on the DTO, so this is directly constructible for
    the purpose of proving the policy."""
    rec = build_recommendation(trade_id="t" * 5000)
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,))
    with pytest.raises(RenderingError):
        pack_message_sections(render_advisory_response(response))


def test_no_trade_huge_explanation_does_not_drop_no_trade_reasons() -> None:
    reason = NoTradeReasonDTO(strategy_family=StrategyFamily.EVENT_DRIVEN, stage=NoTradeStage.RISK, codes=(StrategyIneligibilityReason.QUALITY_UNAVAILABLE,))
    response = build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE, no_trade_reasons=(reason,))
    response = response.model_copy(update={"explanation": response.explanation.model_copy(update={"no_trade_explanation": "e" * 9_000})})

    chunks = pack_message_sections(render_advisory_response(response))  # must not raise
    full_text = "".join(chunks)
    assert "EVENT_DRIVEN" in full_text
    assert "QUALITY_UNAVAILABLE" in full_text
    assert full_text.count("e") >= 9_000
