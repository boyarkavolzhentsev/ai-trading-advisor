"""Telegram command handlers.

The authorization guard runs before any service call or data disclosure, in
every handler, with no exception. Trading logic never lives here: a handler
either replies with a fixed string, or makes exactly one
``ApplicationAdvisoryService.create_advisory`` call and renders whatever
typed result/error comes back - never a second call, never a retry, never a
locally-invented trading decision.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.application.dto import AdvisoryResponse
from app.application.errors import (
    ApplicationInputError,
    ApplicationStateError,
    DuplicateCycleError,
    InternalApplicationError,
)
from app.telegram.identity import TelegramIdentityError, derive_logical_cycle_id
from app.telegram.rendering import RenderingError, pack_message_sections, render_advisory_response

logger = logging.getLogger(__name__)

NOT_AUTHORIZED_MESSAGE = "Not authorized."
START_MESSAGE = (
    "AI Trading Advisor - advisory-only bot.\n"
    "This bot never executes trades, places orders, or modifies positions.\n"
    "/signal - run one fresh advisory cycle\n"
    "/status - show local service status\n"
    "/help - show available commands"
)
HELP_MESSAGE = (
    "/start - welcome message\n"
    "/help - this message\n"
    "/status - local service status (no market/provider call)\n"
    "/signal - run one fresh advisory cycle (no arguments)"
)
SIGNAL_USAGE_MESSAGE = "Usage: /signal"
NON_COMMAND_MESSAGE = "Use /help to see available commands."
APPLICATION_INPUT_ERROR_MESSAGE = "Invalid request. Please try /signal again."
DUPLICATE_CYCLE_MESSAGE = "This request was already processed."
APPLICATION_STATE_ERROR_MESSAGE = "Service unavailable."
INTERNAL_ERROR_MESSAGE = "Internal error occurred."


def _is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    allowlist: frozenset[int] = context.bot_data["allowlist"]
    user = update.effective_user
    return user is not None and user.id in allowlist


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    chat = update.effective_chat
    assert chat is not None  # guaranteed: every registered handler is filters.ChatType.PRIVATE-gated
    await context.bot.send_message(chat_id=chat.id, text=text)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context):
        await _reply(update, context, NOT_AUTHORIZED_MESSAGE)
        return
    await _reply(update, context, START_MESSAGE)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context):
        await _reply(update, context, NOT_AUTHORIZED_MESSAGE)
        return
    await _reply(update, context, HELP_MESSAGE)


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Never calls create_advisory/MT5/Binance/OpenAI/the calendar bridge -
    the fixed symbol is read from bot_data (set once at startup by
    app.telegram.bot.build_bot's own post_init), never re-parsed from the
    environment per request."""
    if not _is_authorized(update, context):
        await _reply(update, context, NOT_AUTHORIZED_MESSAGE)
        return
    symbol = context.bot_data["symbol"]
    await _reply(update, context, f"Service is running.\nSymbol: {symbol}")


async def handle_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context):
        await _reply(update, context, NOT_AUTHORIZED_MESSAGE)
        return

    if context.args:
        # /signal accepts no arguments - never interpreted as a symbol,
        # strategy, or any other parameter, and create_advisory is never
        # called for a malformed invocation like this.
        await _reply(update, context, SIGNAL_USAGE_MESSAGE)
        return

    try:
        logical_cycle_id = derive_logical_cycle_id(update)
    except TelegramIdentityError:
        await _reply(update, context, APPLICATION_INPUT_ERROR_MESSAGE)
        return

    service = context.bot_data["advisory_service"]

    try:
        response = await service.create_advisory(logical_cycle_id=logical_cycle_id)
    except DuplicateCycleError:
        # Same Telegram update -> same logical_cycle_id -> the same logical
        # cycle stays the same cycle. No regenerated identity, no retry, no
        # colliding_trade_ids/persistence-state dump to the chat.
        await _reply(update, context, DUPLICATE_CYCLE_MESSAGE)
        return
    except ApplicationStateError:
        await _reply(update, context, APPLICATION_STATE_ERROR_MESSAGE)
        return
    except ApplicationInputError:
        await _reply(update, context, APPLICATION_INPUT_ERROR_MESSAGE)
        return
    except InternalApplicationError:
        await _reply(update, context, INTERNAL_ERROR_MESSAGE)
        return
    except Exception:  # noqa: BLE001 - deliberate catch-all boundary, sanitized reply only
        logger.exception("unexpected error handling /signal for logical_cycle_id=%s", logical_cycle_id)
        await _reply(update, context, INTERNAL_ERROR_MESSAGE)
        return

    await _send_advisory_response(update, context, response)


async def _send_advisory_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response: AdvisoryResponse) -> None:
    try:
        chunks = pack_message_sections(render_advisory_response(response))
    except RenderingError:
        logger.exception("rendering failed for logical_cycle_id=%s", response.logical_cycle_id)
        await _reply(update, context, INTERNAL_ERROR_MESSAGE)
        return

    for chunk in chunks:
        await _reply(update, context, chunk)


async def handle_non_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Never routes free-form text to an LLM, never interprets it as a
    trading instruction."""
    if not _is_authorized(update, context):
        await _reply(update, context, NOT_AUTHORIZED_MESSAGE)
        return
    await _reply(update, context, NON_COMMAND_MESSAGE)


__all__ = [
    "handle_help",
    "handle_non_command",
    "handle_signal",
    "handle_start",
    "handle_status",
]
