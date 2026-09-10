"""Authorization guard tests: every handler rejects a non-allowlisted user
with a fixed message, before any service call or data disclosure - no
symbol/status/advisory content ever leaks to an unauthorized user."""

from __future__ import annotations

import pytest

from app.telegram.handlers import (
    NOT_AUTHORIZED_MESSAGE,
    handle_help,
    handle_non_command,
    handle_signal,
    handle_start,
    handle_status,
)
from tests.telegram_support import FakeApplicationAdvisoryService, FakeContext, build_advisory_response, build_update

ALLOWED_USER_ID = 42
UNAUTHORIZED_USER_ID = 999


def _context_with_allowlist(service: FakeApplicationAdvisoryService, *, symbol: str = "EURUSD") -> FakeContext:
    return FakeContext(bot_data={"advisory_service": service, "symbol": symbol, "allowlist": frozenset({ALLOWED_USER_ID})})


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [handle_start, handle_help, handle_status, handle_signal, handle_non_command])
async def test_unauthorized_user_rejected_for_every_handler(handler) -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=UNAUTHORIZED_USER_ID)
    context = _context_with_allowlist(fake)
    await handler(update, context)
    assert context.bot.sent_messages == [(update.effective_chat.id, NOT_AUTHORIZED_MESSAGE)]
    assert fake.create_advisory_calls == []


@pytest.mark.asyncio
async def test_unauthorized_status_never_reveals_symbol() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=UNAUTHORIZED_USER_ID)
    context = _context_with_allowlist(fake, symbol="EURUSD")
    await handle_status(update, context)
    sent_text = context.bot.sent_messages[0][1]
    assert sent_text == NOT_AUTHORIZED_MESSAGE
    assert "EURUSD" not in sent_text


@pytest.mark.asyncio
async def test_unauthorized_signal_never_reveals_advisory_state() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=UNAUTHORIZED_USER_ID)
    context = _context_with_allowlist(fake)
    await handle_signal(update, context)
    sent_text = context.bot.sent_messages[0][1]
    assert sent_text == NOT_AUTHORIZED_MESSAGE
    assert "READY" not in sent_text
    assert "NO_TRADE" not in sent_text


@pytest.mark.asyncio
async def test_authorized_user_proceeds_past_the_guard() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=ALLOWED_USER_ID)
    context = _context_with_allowlist(fake)
    await handle_start(update, context)
    assert context.bot.sent_messages[0][1] != NOT_AUTHORIZED_MESSAGE


@pytest.mark.asyncio
async def test_authorization_checked_before_any_derive_or_service_call() -> None:
    """A user who is not in the allowlist must never even reach identity
    derivation/create_advisory for /signal - not just "the reply happens to
    be Not authorized", but genuinely zero downstream calls."""
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    update = build_update(user_id=UNAUTHORIZED_USER_ID, chat_id=555, update_id=1000)
    context = _context_with_allowlist(fake)
    await handle_signal(update, context)
    assert fake.create_advisory_calls == []
