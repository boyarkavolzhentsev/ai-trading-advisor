"""``AdvisoryResponse`` -> plain-text Telegram rendering. Pure functions only
- no Telegram network call anywhere in this module.

Two disjoint concerns, never mixed: authoritative trade geometry
(``render_recommendation``, sourced only from ``RecommendationDTO``) and
presentation-only narrative (``render_explanation``, sourced only from
``ExplanationDTO``) - the explanation section can never alter which
recommendation/no-trade section was rendered, only append additional
context after it.

Decimal fields are rendered via ``str(Decimal)`` - never through ``float`` -
preserving exact textual precision. Timestamps are rendered as explicit UTC
ISO-8601 (``value.astimezone(UTC).isoformat()``); an unexpectedly naive
timestamp fails rendering (``RenderingError``) rather than silently being
treated as UTC. Plain text only - no Markdown/HTML parse mode - avoids any
escaping/parse-injection risk from LLM-authored ``headline``/``cycle_summary``/
``warnings`` text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.application.dto import (
    AdvisoryResponse,
    ApplicationAdvisoryStatus,
    ExplanationDTO,
    NoTradeReasonDTO,
    RecommendationDTO,
)

_DEFAULT_MAX_CHUNK_SIZE = 4000
"""Telegram's own ``sendMessage`` hard limit is 4096 UTF-8 characters
(server-enforced); this safety maximum leaves headroom rather than targeting
the exact boundary."""


class RenderingError(Exception):
    """Raised when rendering cannot safely proceed - an unexpectedly naive
    timestamp, or a single atomic message section that itself exceeds the
    packing safety limit. Never silently truncates/guesses authoritative
    trade geometry."""


def format_decimal(value: Decimal) -> str:
    """Never ``float(value)`` - preserves exact textual precision (e.g.
    ``Decimal("1.10000")`` renders as ``"1.10000"``, never ``"1.1"``)."""
    return str(value)


def format_timestamp(value: datetime) -> str:
    """Explicit UTC ISO-8601. Fails closed (``RenderingError``) on a naive
    ``datetime`` rather than silently assuming it is already UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise RenderingError(f"expected a timezone-aware datetime, got a naive one: {value!r}")
    return value.astimezone(UTC).isoformat()


def render_recommendation(rec: RecommendationDTO) -> str:
    """Every authoritative field, verbatim - never truncated, never
    reordered relative to the DTO's own field values."""
    take_profit_levels = ", ".join(format_decimal(level) for level in rec.take_profit_levels) or "none"
    lines = [
        f"Trade: {rec.trade_id}",
        f"Symbol: {rec.symbol}",
        f"Strategy: {rec.strategy_family.value}",
        f"Direction: {rec.direction.value}",
        f"Entry: {format_decimal(rec.entry_price)}",
        f"Stop: {format_decimal(rec.stop_loss)}",
        f"Take-profit: {take_profit_levels}",
        f"Volume: {format_decimal(rec.approved_volume)}",
        f"Risk: {format_decimal(rec.approved_risk_amount)} {rec.account_currency}",
        f"Signal time: {format_timestamp(rec.signal_time)}",
        f"Valid until: {format_timestamp(rec.valid_until)}",
    ]
    return "\n".join(lines)


def render_no_trade_reason(reason: NoTradeReasonDTO) -> str:
    """Raw enum values preserved directly (V1 preference over an invented
    mapping) - e.g. ``"TREND_FOLLOWING — SETUP: MISSING_STOP_REFERENCE"``."""
    codes = ", ".join(code.value for code in reason.codes)
    return f"{reason.strategy_family.value} — {reason.stage.value}: {codes}"


def render_degraded_diagnostics(response: AdvisoryResponse) -> str:
    """Concise, DTO-sourced facts only - never the whole diagnostics object
    dumped verbatim."""
    data_quality = response.data_quality
    diagnostics = response.diagnostics
    lines = ["Diagnostics:"]

    if data_quality.technical_fetch_failed_timeframes:
        timeframes = ", ".join(tf.value for tf in data_quality.technical_fetch_failed_timeframes)
        lines.append(f"- Technical fetch failed: {timeframes}")

    lines.append(f"- Account risk snapshot ready: {data_quality.account_risk_snapshot_ready}")
    if data_quality.account_risk_snapshot_block_reasons:
        reasons = ", ".join(reason.value for reason in data_quality.account_risk_snapshot_block_reasons)
        lines.append(f"- Account risk snapshot blocked: {reasons}")

    lines.append(f"- LLM provider status: {diagnostics.llm_provider_status.value}")
    lines.append(f"- Deterministic fallback used: {response.explanation.deterministic_fallback_used}")

    failed_issuance = [
        entry for entry in diagnostics.issuance_persistence if not (entry.tracking_persisted and entry.provenance_persisted)
    ]
    if failed_issuance:
        lines.append(f"- Issuance persistence issues: {len(failed_issuance)}")

    return "\n".join(lines)


def render_explanation(explanation: ExplanationDTO) -> str | None:
    """Presentation only - never able to alter direction/entry/stop/TP/
    volume/risk/whether a recommendation exists. Returns ``None`` (no
    section) when there is nothing to show."""
    lines: list[str] = []
    if explanation.headline:
        lines.append(explanation.headline)
    if explanation.cycle_summary:
        lines.append(explanation.cycle_summary)
    if explanation.no_trade_explanation:
        lines.append(explanation.no_trade_explanation)
    if explanation.warnings:
        lines.append("Warnings: " + "; ".join(explanation.warnings))
    if explanation.risk_notes:
        lines.append("Risk notes: " + "; ".join(explanation.risk_notes))
    if explanation.data_quality_notes:
        lines.append("Data quality notes: " + "; ".join(explanation.data_quality_notes))
    return "\n".join(lines) if lines else None


def split_narrative_text(text: str, *, max_size: int = _DEFAULT_MAX_CHUNK_SIZE) -> list[str]:
    """Deterministically splits arbitrary presentation-only text into
    ``<=max_size`` pieces, preserving order - concatenating the returned
    pieces reproduces ``text`` exactly, character for character. Used only
    for ``ExplanationDTO``'s free-form LLM/deterministic-fallback-authored
    text (``headline``/``cycle_summary``/``no_trade_explanation``/
    ``warnings``/``risk_notes``/``data_quality_notes`` carry no length
    constraint at all - confirmed directly from ``app.application.dto``).

    Never used for an authoritative ``render_recommendation`` block, which
    must remain atomic and raise (never be split) if oversized - see the
    approved pre-commit rendering-safety review, "6. MESSAGE-SIZE POLICY -
    CORRECTIVE RULE": a presentation-only narrative must never be able to
    suppress delivery of an already-approved recommendation merely by being
    unexpectedly long.
    """
    if not text:
        return []
    if len(text) <= max_size:
        return [text]
    return [text[i : i + max_size] for i in range(0, len(text), max_size)]


def render_header(response: AdvisoryResponse) -> str:
    return (
        f"Symbol: {response.symbol}\n"
        f"Status: {response.status.value}\n"
        f"As of: {format_timestamp(response.as_of)}\n"
        f"Cycle: {response.logical_cycle_id}"
    )


def render_advisory_response(response: AdvisoryResponse) -> list[str]:
    """Returns an ordered list of independent message *sections* - never
    pre-packed into chunks (see ``pack_message_sections``). Supports zero,
    one, or many ``recommendations``/``no_trade_reasons`` - never assumes
    exactly one, and always preserves the DTO's own order.

    Send-order invariant (approved pre-commit rendering-safety review, "9.
    SEND ORDER"): header -> DEGRADED marker -> every recommendation (in DTO
    order) -> every no-trade reason (in DTO order, enum-only, genuinely
    bounded - confirmed from ``NoTradeCode``'s own closed union of StrEnum
    types, never caller/provider free text) -> degraded diagnostics
    (confirmed enum/bool/count-only, genuinely bounded - see
    ``render_degraded_diagnostics``) -> presentation-only narrative last,
    pre-split via ``split_narrative_text`` so its own unbounded length can
    never raise ``RenderingError`` and can therefore never suppress an
    already-approved recommendation that was already appended earlier in
    this same list.
    """
    sections: list[str] = [render_header(response)]

    if response.status is ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE:
        sections.append("SERVICE UNAVAILABLE\nNo recommendation available this cycle.")
        return sections

    if response.status is ApplicationAdvisoryStatus.DEGRADED:
        sections.append("DEGRADED — this cycle's data/service quality was degraded.")

    if response.recommendations:
        sections.extend(render_recommendation(rec) for rec in response.recommendations)
    else:
        sections.append("NO TRADE")

    sections.extend(render_no_trade_reason(reason) for reason in response.no_trade_reasons)

    if response.status is ApplicationAdvisoryStatus.DEGRADED:
        sections.append(render_degraded_diagnostics(response))

    explanation_section = render_explanation(response.explanation)
    if explanation_section is not None:
        sections.extend(split_narrative_text(explanation_section))

    return sections


def pack_message_sections(sections: list[str], *, max_chunk_size: int = _DEFAULT_MAX_CHUNK_SIZE) -> list[str]:
    """Deterministic, section-preserving packing: sections are never split
    across chunks, and are never reordered. A single section that itself
    exceeds ``max_chunk_size`` raises ``RenderingError`` rather than being
    silently truncated - this applies uniformly to every section (including
    a ``render_recommendation`` block), so authoritative trade geometry can
    never be cut."""
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for section in sections:
        if len(section) > max_chunk_size:
            raise RenderingError(
                f"a single message section is {len(section)} characters, exceeding the "
                f"{max_chunk_size}-character safety limit - content is never truncated"
            )
        separator_length = 2 if current else 0  # "\n\n" between sections in the same chunk
        if current and current_length + separator_length + len(section) > max_chunk_size:
            chunks.append("\n\n".join(current))
            current = [section]
            current_length = len(section)
        else:
            current.append(section)
            current_length += separator_length + len(section)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


__all__ = [
    "RenderingError",
    "format_decimal",
    "format_timestamp",
    "pack_message_sections",
    "render_advisory_response",
    "render_degraded_diagnostics",
    "render_explanation",
    "render_header",
    "render_no_trade_reason",
    "render_recommendation",
    "split_narrative_text",
]
