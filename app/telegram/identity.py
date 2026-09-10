"""Telegram ``logical_cycle_id`` derivation - pure functions only.

Reuses Telegram's own ``update_id`` (a per-bot, strictly sequential,
redelivery-aware identifier Telegram's own documentation describes as
existing specifically so a consumer can "ignore repeated updates") rather
than inventing a UUID/random/wall-clock-derived value - mirrors
``app.application.identity``'s own "never generates an identity" discipline
one layer up. No fallback identity is ever invented: an ``Update`` with no
``effective_chat`` fails closed via ``TelegramIdentityError``.

Format: ``tg_<chat_id>_<update_id>`` - both components are plain integers
(``chat_id`` may carry a leading ``-`` for a non-private chat, itself within
the Application layer's ``[A-Za-z0-9_-]`` charset), so the derived string
satisfies ``app.application.identity``'s ``[A-Za-z0-9_-]{1,128}`` regex by
construction, well under the length bound for any realistic Telegram id
range.
"""

from __future__ import annotations

from telegram import Update


class TelegramIdentityError(Exception):
    """Raised when an incoming ``Update`` carries no ``effective_chat`` -
    there is nothing safe to derive a ``logical_cycle_id`` from. Never
    falls back to a generated/random identity."""


def derive_logical_cycle_id(update: Update) -> str:
    """Deterministic: the same ``Update`` (same ``effective_chat.id``/
    ``update_id``) always derives the identical string; a different
    ``update_id`` always derives a different string. No ``uuid``/``random``/
    wall-clock read/``hash()`` anywhere in this module."""
    chat = update.effective_chat
    if chat is None:
        raise TelegramIdentityError("update has no effective_chat; cannot derive a logical_cycle_id")
    return f"tg_{chat.id}_{update.update_id}"


__all__ = ["TelegramIdentityError", "derive_logical_cycle_id"]
