"""Telegram-specific transport configuration.

Owns ONLY ``TELEGRAM_BOT_TOKEN``/``TELEGRAM_ALLOWED_USER_IDS`` parsing - never
duplicates shared production configuration (symbol/market/contract_type/MT5/
calendar/LLM), which remains ``app.bootstrap.production``'s exclusive
responsibility (see the approved Telegram design audit, "28. CONFIG /
BOOTSTRAP").

Every error raised here is a sanitized ``TelegramConfigurationError`` naming
only the environment *variable*, never its value - mirrors
``app.bootstrap.production.BootstrapConfigurationError``'s own discipline one
package over. ``TELEGRAM_BOT_TOKEN`` is deliberately returned as a plain
``str``, never a ``SecretStr``: python-telegram-bot's own
``ApplicationBuilder.token()`` requires a plain string immediately, so
wrapping it would force an instant unwrap with no protective benefit (see the
approved design audit, "12. BOT TOKEN") - it is never logged, never placed in
any error message, and never included in any DTO/repr, enforced by this
module's own hygiene test rather than by a wrapper type.
"""

from __future__ import annotations

import os
import re

_USER_ID_PATTERN = re.compile(r"^[0-9]+$")


class TelegramConfigurationError(Exception):
    """Raised when Telegram-specific environment configuration is missing or
    malformed. Every message names only the environment variable, never a
    value - especially never ``TELEGRAM_BOT_TOKEN``'s content, and never the
    specific malformed ``TELEGRAM_ALLOWED_USER_IDS`` entry."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise TelegramConfigurationError(f"Missing required environment variable: {name}")
    return value


def build_telegram_bot_token_from_env() -> str:
    """Required, non-empty, non-whitespace-only. Plain ``str`` - see this
    module's own docstring for why no ``SecretStr`` wrapper is used."""
    return _require_env("TELEGRAM_BOT_TOKEN")


def build_telegram_allowlist_from_env() -> frozenset[int]:
    """``TELEGRAM_ALLOWED_USER_IDS``: comma-separated positive integers,
    whitespace trimmed, duplicates harmless (collapsed by the resulting
    ``frozenset``). Missing, empty, or containing any non-positive-integer
    entry (including an empty segment from a stray/trailing comma) all fail
    loudly with ``TelegramConfigurationError`` - an empty allowlist is never
    interpreted as "allow everyone"."""
    raw = _require_env("TELEGRAM_ALLOWED_USER_IDS")
    entries = [item.strip() for item in raw.split(",")]

    ids: set[int] = set()
    for entry in entries:
        if not _USER_ID_PATTERN.fullmatch(entry):
            raise TelegramConfigurationError(
                "Invalid value for environment variable: TELEGRAM_ALLOWED_USER_IDS "
                "(expected a comma-separated list of positive integers)"
            )
        value = int(entry)
        if value <= 0:
            raise TelegramConfigurationError(
                "Invalid value for environment variable: TELEGRAM_ALLOWED_USER_IDS "
                "(expected a comma-separated list of positive integers)"
            )
        ids.add(value)

    if not ids:
        raise TelegramConfigurationError("TELEGRAM_ALLOWED_USER_IDS must contain at least one positive integer user id")

    return frozenset(ids)


__all__ = [
    "TelegramConfigurationError",
    "build_telegram_allowlist_from_env",
    "build_telegram_bot_token_from_env",
]
