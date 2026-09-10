"""``app.telegram.identity`` tests: deterministic logical_cycle_id
derivation from Telegram's own update_id/chat_id - no UUID/random/time."""

from __future__ import annotations

import ast
import inspect

import pytest

import app.telegram.identity as identity_module
from app.telegram.identity import TelegramIdentityError, derive_logical_cycle_id
from tests.telegram_support import build_update

_LOGICAL_CYCLE_ID_PATTERN = __import__("re").compile(r"^[A-Za-z0-9_-]{1,128}$")


def test_same_update_same_id() -> None:
    update = build_update(chat_id=555, update_id=1000)
    assert derive_logical_cycle_id(update) == derive_logical_cycle_id(update)


def test_same_chat_and_update_id_values_produce_same_id() -> None:
    first = build_update(chat_id=555, update_id=1000)
    second = build_update(chat_id=555, update_id=1000)
    assert derive_logical_cycle_id(first) == derive_logical_cycle_id(second)


def test_different_update_id_different_result() -> None:
    first = build_update(chat_id=555, update_id=1000)
    second = build_update(chat_id=555, update_id=1001)
    assert derive_logical_cycle_id(first) != derive_logical_cycle_id(second)


def test_different_chat_id_different_result() -> None:
    first = build_update(chat_id=555, update_id=1000)
    second = build_update(chat_id=556, update_id=1000)
    assert derive_logical_cycle_id(first) != derive_logical_cycle_id(second)


def test_exact_format() -> None:
    update = build_update(chat_id=555, update_id=1000)
    assert derive_logical_cycle_id(update) == "tg_555_1000"


def test_negative_chat_id_still_safe_charset() -> None:
    """A non-private chat's negative id must still produce a charset-safe
    result (the leading '-' is within [A-Za-z0-9_-])."""
    update = build_update(chat_id=-100123456789, update_id=42, private=False)
    result = derive_logical_cycle_id(update)
    assert result == "tg_-100123456789_42"
    assert _LOGICAL_CYCLE_ID_PATTERN.fullmatch(result)


def test_result_matches_application_safe_charset() -> None:
    update = build_update(chat_id=555, update_id=1000)
    result = derive_logical_cycle_id(update)
    assert _LOGICAL_CYCLE_ID_PATTERN.fullmatch(result)


def test_result_length_bounded() -> None:
    update = build_update(chat_id=-100123456789012, update_id=999999999999)
    result = derive_logical_cycle_id(update)
    assert len(result) <= 128


def test_no_effective_chat_raises_identity_error() -> None:
    from telegram import Update

    bare_update = Update(update_id=1)  # no message -> effective_chat is None
    with pytest.raises(TelegramIdentityError):
        derive_logical_cycle_id(bare_update)


def test_identity_module_never_uses_uuid_random_or_time() -> None:
    """AST-based (not substring) - mirrors
    tests/test_application_identity.py's own established pattern."""
    tree = ast.parse(inspect.getsource(identity_module))
    forbidden_names = {"uuid4", "uuid", "random", "secrets", "hash"}
    forbidden_attrs = {"now", "utcnow"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_names for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_attrs
