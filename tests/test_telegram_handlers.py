"""Authorized-flow handler tests: /start, /help, /status, /signal (normal,
argument-usage, duplicate, error mapping, status rendering)."""

from __future__ import annotations

import pytest

from app.application.dto import ApplicationAdvisoryStatus
from app.application.errors import ApplicationInputError, ApplicationStateError, DuplicateCycleError, InternalApplicationError
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.telegram.handlers import (
    APPLICATION_INPUT_ERROR_MESSAGE,
    APPLICATION_STATE_ERROR_MESSAGE,
    DUPLICATE_CYCLE_MESSAGE,
    HELP_MESSAGE,
    INTERNAL_ERROR_MESSAGE,
    SIGNAL_USAGE_MESSAGE,
    START_MESSAGE,
    handle_help,
    handle_signal,
    handle_start,
    handle_status,
)
from tests.telegram_support import (
    FakeApplicationAdvisoryService,
    FakeContext,
    build_advisory_response,
    build_recommendation,
    build_update,
)

ALLOWED_USER_ID = 42


def _authorized_context(service: FakeApplicationAdvisoryService, *, symbol: str = "EURUSD") -> FakeContext:
    return FakeContext(bot_data={"advisory_service": service, "symbol": symbol, "allowlist": frozenset({ALLOWED_USER_ID})})


@pytest.mark.asyncio
async def test_start_authorized() -> None:
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(FakeApplicationAdvisoryService())
    await handle_start(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, START_MESSAGE)]


@pytest.mark.asyncio
async def test_help_authorized_lists_exactly_four_commands() -> None:
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(FakeApplicationAdvisoryService())
    await handle_help(update, context)
    sent_text = context.bot.sent_messages[0][1]
    assert sent_text == HELP_MESSAGE
    for command in ("/start", "/help", "/status", "/signal"):
        assert command in sent_text


@pytest.mark.asyncio
async def test_status_authorized_no_service_call() -> None:
    fake = FakeApplicationAdvisoryService()
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake, symbol="EURUSD")
    await handle_status(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, "Service is running.\nSymbol: EURUSD")]
    assert fake.create_advisory_calls == []


# --- /signal -----------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_normal_flow_exactly_one_call_with_derived_id() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE))
    update = build_update(user_id=ALLOWED_USER_ID, chat_id=555, update_id=1000)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert fake.create_advisory_calls == ["tg_555_1000"]


@pytest.mark.asyncio
async def test_signal_with_arguments_returns_usage_and_never_calls_service() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=ALLOWED_USER_ID)
    context = FakeContext(bot_data={"advisory_service": fake, "symbol": "EURUSD", "allowlist": frozenset({ALLOWED_USER_ID})}, args=["BTCUSDT"])
    await handle_signal(update, context)
    assert fake.create_advisory_calls == []
    assert context.bot.sent_messages == [(update.effective_chat.id, SIGNAL_USAGE_MESSAGE)]


@pytest.mark.asyncio
async def test_signal_no_retry_exactly_one_call() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert len(fake.create_advisory_calls) == 1


@pytest.mark.asyncio
async def test_signal_duplicate_cycle_error() -> None:
    fake = FakeApplicationAdvisoryService(
        create_advisory_exception=DuplicateCycleError(logical_cycle_id="tg_555_1000", colliding_trade_ids=("tg_555_1000__TREND_FOLLOWING",))
    )
    update = build_update(user_id=ALLOWED_USER_ID, chat_id=555, update_id=1000)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, DUPLICATE_CYCLE_MESSAGE)]
    assert len(fake.create_advisory_calls) == 1
    # never re-derived / never surfaced to the operator
    assert "tg_555_1000__TREND_FOLLOWING" not in context.bot.sent_messages[0][1]


@pytest.mark.asyncio
async def test_signal_application_state_error() -> None:
    fake = FakeApplicationAdvisoryService(create_advisory_exception=ApplicationStateError("run_cycle() requires a started composer"))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, APPLICATION_STATE_ERROR_MESSAGE)]
    assert "composer" not in context.bot.sent_messages[0][1]


@pytest.mark.asyncio
async def test_signal_application_input_error() -> None:
    fake = FakeApplicationAdvisoryService(create_advisory_exception=ApplicationInputError("logical_cycle_id must match [...]; got 'bad'"))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, APPLICATION_INPUT_ERROR_MESSAGE)]
    assert "bad" not in context.bot.sent_messages[0][1]


@pytest.mark.asyncio
async def test_signal_internal_application_error() -> None:
    fake = FakeApplicationAdvisoryService(create_advisory_exception=InternalApplicationError("advisory cycle failed unexpectedly"))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, INTERNAL_ERROR_MESSAGE)]
    assert "failed unexpectedly" not in context.bot.sent_messages[0][1]


@pytest.mark.asyncio
async def test_signal_unexpected_exception_with_fake_secret_never_leaks() -> None:
    secret = "sk-FAKE-SECRET-abcdef123456"
    fake = FakeApplicationAdvisoryService(create_advisory_exception=RuntimeError(f"connection failed, api_key={secret}"))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    assert len(context.bot.sent_messages) == 1
    sent_text = context.bot.sent_messages[0][1]
    assert sent_text == INTERNAL_ERROR_MESSAGE
    assert secret not in sent_text


# --- /signal rendering end-to-end -------------------------------------


@pytest.mark.asyncio
async def test_signal_ready_rendering_reaches_chat() -> None:
    rec = build_recommendation()
    fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,)))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    full_text = "\n".join(text for _, text in context.bot.sent_messages)
    assert rec.trade_id in full_text
    assert "READY" in full_text


@pytest.mark.asyncio
async def test_signal_degraded_rendering_preserves_recommendation() -> None:
    rec = build_recommendation()
    fake = FakeApplicationAdvisoryService(
        result=build_advisory_response(status=ApplicationAdvisoryStatus.DEGRADED, recommendations=(rec,), runtime_outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED)
    )
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    full_text = "\n".join(text for _, text in context.bot.sent_messages)
    assert "DEGRADED" in full_text
    assert rec.trade_id in full_text


@pytest.mark.asyncio
async def test_signal_service_unavailable_rendering() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE))
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)
    await handle_signal(update, context)
    full_text = "\n".join(text for _, text in context.bot.sent_messages)
    assert "SERVICE UNAVAILABLE" in full_text


@pytest.mark.asyncio
async def test_signal_recommendation_delivered_despite_huge_narrative() -> None:
    """End-to-end regression test for the pre-commit rendering-safety
    review's finding: a huge cycle_summary must never cause the handler to
    fall back to "Internal error occurred." while silently dropping an
    already-approved recommendation."""
    rec = build_recommendation()
    response = build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(rec,))
    response = response.model_copy(update={"explanation": response.explanation.model_copy(update={"cycle_summary": "x" * 10_000})})
    fake = FakeApplicationAdvisoryService(result=response)
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _authorized_context(fake)

    await handle_signal(update, context)

    assert len(context.bot.sent_messages) > 1  # split into multiple chunks
    full_text = "\n".join(text for _, text in context.bot.sent_messages)
    assert rec.trade_id in full_text
    assert full_text != INTERNAL_ERROR_MESSAGE
    for _, text in context.bot.sent_messages:
        assert len(text) <= 4000
