"""``app.telegram.config`` tests: token/allowlist parsing, strict fail-loud
behavior, no secret leakage into error messages."""

from __future__ import annotations

import pytest

from app.telegram.config import (
    TelegramConfigurationError,
    build_telegram_allowlist_from_env,
    build_telegram_bot_token_from_env,
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)


# --- token ---------------------------------------------------------------


def test_token_missing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        build_telegram_bot_token_from_env()


def test_token_empty_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        build_telegram_bot_token_from_env()


def test_token_whitespace_only_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        build_telegram_bot_token_from_env()


def test_token_returned_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:AAFakeTokenValue")
    assert build_telegram_bot_token_from_env() == "123456789:AAFakeTokenValue"


def test_token_error_message_never_contains_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(TelegramConfigurationError) as exc_info:
        build_telegram_bot_token_from_env()
    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value)


# --- allowlist -------------------------------------------------------------


def test_allowlist_missing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_ALLOWED_USER_IDS"):
        build_telegram_allowlist_from_env()


def test_allowlist_empty_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "")
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_ALLOWED_USER_IDS"):
        build_telegram_allowlist_from_env()


@pytest.mark.parametrize("malformed", ["abc", "12,abc", "12,,34", "12, ,34", "-5", "12,-5", "1.5", "12,"])
def test_allowlist_malformed_fails(monkeypatch: pytest.MonkeyPatch, malformed: str) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", malformed)
    with pytest.raises(TelegramConfigurationError, match="TELEGRAM_ALLOWED_USER_IDS"):
        build_telegram_allowlist_from_env()


def test_allowlist_one_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    assert build_telegram_allowlist_from_env() == frozenset({42})


def test_allowlist_multiple_users(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42,43,44")
    assert build_telegram_allowlist_from_env() == frozenset({42, 43, 44})


def test_allowlist_whitespace_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", " 42 , 43 ")
    assert build_telegram_allowlist_from_env() == frozenset({42, 43})


def test_allowlist_duplicates_harmless(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42,42,43")
    assert build_telegram_allowlist_from_env() == frozenset({42, 43})


def test_allowlist_result_is_frozenset_of_int() -> None:
    import os

    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "42"
    try:
        result = build_telegram_allowlist_from_env()
        assert isinstance(result, frozenset)
        assert all(isinstance(item, int) for item in result)
    finally:
        del os.environ["TELEGRAM_ALLOWED_USER_IDS"]
