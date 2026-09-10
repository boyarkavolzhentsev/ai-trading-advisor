"""Shared fixtures for ``app.telegram`` tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.

Constructs real, offline ``telegram.Update``/``Chat``/``User``/``Message``
objects (pure Python objects, no network attachment needed for property
access - verified directly against the installed python-telegram-bot 22.8)
rather than mocks, for real fidelity of ``effective_chat``/``effective_user``/
``update_id``. ``FakeContext``/``FakeBot`` stand in for PTB's own
``CallbackContext``/``Bot`` - handlers only ever touch ``context.bot_data``,
``context.args``, and ``context.bot.send_message``, so a minimal duck-typed
stand-in is sufficient and avoids the network-bound machinery a real
``Bot``/``CallbackContext`` would otherwise require.
"""

from __future__ import annotations

from datetime import UTC, datetime

from telegram import Chat, Message, Update, User

from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response, build_recommendation

__all__ = [
    "FakeApplicationAdvisoryService",
    "FakeBot",
    "FakeContext",
    "build_advisory_response",
    "build_recommendation",
    "build_update",
]


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent_messages.append((chat_id, text))


class FakeContext:
    """Duck-typed stand-in for ``telegram.ext.ContextTypes.DEFAULT_TYPE`` -
    carries exactly the three attributes every handler in
    ``app.telegram.handlers`` reads: ``bot_data``, ``args``, ``bot``."""

    def __init__(self, *, bot_data: dict[str, object], args: list[str] | None = None) -> None:
        self.bot_data = bot_data
        self.args = args if args is not None else []
        self.bot = FakeBot()


def build_update(*, chat_id: int = 555, user_id: int = 42, update_id: int = 1000, text: str = "/signal", private: bool = True) -> Update:
    chat = Chat(id=chat_id, type=Chat.PRIVATE if private else Chat.GROUP)
    user = User(id=user_id, is_bot=False, first_name="Operator")
    message = Message(message_id=1, date=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC), chat=chat, from_user=user, text=text)
    return Update(update_id=update_id, message=message)
