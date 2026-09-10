"""``build_bot``/lifecycle tests: exact handler registration, one startup/
one shutdown via post_init/post_shutdown, same service instance reused,
startup failure propagates - all offline, never calling PTB's own
``initialize()``/``run_polling()``/any Telegram Bot API method.

``application.post_init``/``application.post_shutdown`` expose the exact
coroutine closures ``build_bot`` registered (verified directly against the
installed python-telegram-bot 22.8) - calling them directly here exercises
the real wiring without ever entering PTB's own initialize/start/stop
orchestration or opening a network connection.

Pre-commit lifecycle review finding (traced directly from the installed
``telegram/ext/_application.py::Application.__run``, not assumed): PTB's own
``run_polling`` ``finally:`` block unconditionally calls
``self.shutdown()``/``self.post_shutdown(self)`` regardless of whether
``post_init`` raised - only ``(KeyboardInterrupt, SystemExit)`` are caught by
the surrounding ``try``, but Python's ``finally`` always runs even when an
*uncaught* exception is propagating through the ``try`` block. This means our
``post_shutdown`` callback WILL be invoked by PTB even after a failed
``service.startup()``. This is proven safe (not merely assumed) by
``app.production_advisory.composer.ProductionAdvisoryComposer.shutdown``'s
own explicit, documented contract: "Always idempotent, including from NEW...
shutdown never raises" - see
``test_post_shutdown_after_failed_startup_is_safe_with_real_composer`` below,
which exercises the REAL ``ApplicationAdvisoryService``/
``ProductionAdvisoryComposer`` (not a mock) to prove this rather than assert
it. No ``started`` boolean guard was added to ``app/telegram/bot.py`` as a
result - one would be unnecessary complexity given this proven, existing
Stage0D contract (see the approved pre-commit review, "2. SERVICE SHUTDOWN
AFTER FAILED STARTUP").
"""

from __future__ import annotations

import pytest
from telegram.ext import CommandHandler, MessageHandler

from app.telegram.bot import build_bot
from tests.telegram_support import FakeApplicationAdvisoryService

_FAKE_TOKEN = "123456789:AAFakeTokenForOfflineTestsOnlyNotReal"


class _FailingStartupService:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    async def startup(self) -> None:
        raise RuntimeError("startup boom")

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def create_advisory(self, *, logical_cycle_id: str):
        raise NotImplementedError


# --- bot factory construction -----------------------------------------------


def test_build_bot_registers_exactly_four_command_handlers_and_one_message_handler() -> None:
    fake = FakeApplicationAdvisoryService()
    app = build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42}))
    handlers = app.handlers[0]
    command_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    message_handlers = [h for h in handlers if isinstance(h, MessageHandler)]
    assert len(command_handlers) == 4
    assert len(message_handlers) == 1
    registered_commands = {command for h in command_handlers for command in h.commands}
    assert registered_commands == {"start", "help", "status", "signal"}


def test_build_bot_handlers_are_private_chat_only() -> None:
    from telegram.ext import filters as ptb_filters

    fake = FakeApplicationAdvisoryService()
    app = build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42}))
    for handler in app.handlers[0]:
        # every registered handler must filter on ChatType.PRIVATE somewhere
        # in its filter expression - checked via the filter's own repr,
        # since PTB composes filters into a tree rather than a flat list.
        assert "PRIVATE" in repr(handler.filters)


def test_build_bot_never_calls_run_polling_or_initialize(monkeypatch: pytest.MonkeyPatch) -> None:
    from telegram.ext import Application as PTBApplication

    def _forbidden(*args, **kwargs):
        raise AssertionError("build_bot must never call initialize/start/run_polling")

    monkeypatch.setattr(PTBApplication, "run_polling", _forbidden)
    monkeypatch.setattr(PTBApplication, "initialize", _forbidden)
    fake = FakeApplicationAdvisoryService()
    build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42}))  # must not raise


# --- lifecycle: post_init / post_shutdown -----------------------------------


@pytest.mark.asyncio
async def test_post_init_starts_service_and_populates_bot_data() -> None:
    fake = FakeApplicationAdvisoryService()
    app = build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42, 43}))

    await app.post_init(app)

    assert fake.startup_calls == 1
    assert app.bot_data["advisory_service"] is fake
    assert app.bot_data["symbol"] == "EURUSD"
    assert app.bot_data["allowlist"] == frozenset({42, 43})


@pytest.mark.asyncio
async def test_post_shutdown_stops_service_exactly_once() -> None:
    fake = FakeApplicationAdvisoryService()
    app = build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42}))

    await app.post_init(app)
    await app.post_shutdown(app)

    assert fake.startup_calls == 1
    assert fake.shutdown_calls == 1


@pytest.mark.asyncio
async def test_same_service_instance_reused_across_lifecycle() -> None:
    fake = FakeApplicationAdvisoryService()
    app = build_bot(token=_FAKE_TOKEN, service=fake, symbol="EURUSD", allowlist=frozenset({42}))
    await app.post_init(app)
    assert app.bot_data["advisory_service"] is fake  # identity check, not just a count


@pytest.mark.asyncio
async def test_post_init_failure_propagates_and_post_init_itself_never_calls_shutdown() -> None:
    """``post_init`` itself only calls ``service.startup()`` - it never
    calls ``shutdown()`` on any path. This is narrower than "PTB never calls
    post_shutdown after a failed post_init" (it does - see
    ``test_post_shutdown_after_failed_startup_is_safe_with_real_composer``
    below): this test only proves our own ``post_init`` closure's own
    behavior in isolation."""
    failing_service = _FailingStartupService()
    app = build_bot(token=_FAKE_TOKEN, service=failing_service, symbol="EURUSD", allowlist=frozenset({42}))

    with pytest.raises(RuntimeError, match="startup boom"):
        await app.post_init(app)

    assert failing_service.shutdown_calls == 0


@pytest.mark.asyncio
async def test_post_shutdown_after_failed_startup_is_safe_with_real_composer() -> None:
    """PTB's real run_polling always reaches post_shutdown, even when
    post_init raised (see this module's own docstring, traced directly from
    the installed python-telegram-bot 22.8 source). This test proves the
    REAL ApplicationAdvisoryService -> ProductionAdvisoryComposer chain (not
    a mock) tolerates exactly that sequence: startup() fails part-way
    through (leaving the composer's lifecycle_state at "NEW", never
    advanced to "STARTED"), and shutdown() afterward must not raise -
    exactly as ProductionAdvisoryComposer.shutdown()'s own docstring
    guarantees ("Always idempotent, including from NEW... shutdown never
    raises")."""
    from app.application.advisory_service import ApplicationAdvisoryService
    from app.production_advisory.composer import ProductionAdvisoryComposer
    from tests.production_advisory_support import FakeMT5Client, FakeRecordPersistence, build_config

    class FailingFlowBootstrap:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def start(self) -> None:
            raise RuntimeError("flow bootstrap start failed")

        async def stop(self) -> None:
            self.stop_calls += 1

        def build_flow_result(self, *, as_of: object) -> None:
            raise AssertionError("build_flow_result should not be called in this test")

        def health(self) -> None:
            raise AssertionError("health() should not be called in this test")

    flow = FailingFlowBootstrap()
    composer = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=flow,
        mt5_client=FakeMT5Client(),
        tracking_persistence=FakeRecordPersistence(),
        provenance_persistence=FakeRecordPersistence(),
    )
    service = ApplicationAdvisoryService(composer=composer)
    app = build_bot(token=_FAKE_TOKEN, service=service, symbol="EURUSD", allowlist=frozenset({42}))

    with pytest.raises(RuntimeError, match="flow bootstrap start failed"):
        await app.post_init(app)

    # PTB's real __run always reaches post_shutdown in its finally: block,
    # regardless of what happened above - this must not raise.
    await app.post_shutdown(app)

    assert flow.stop_calls == 1  # composer.shutdown() -> flow_bootstrap.stop(), proven idempotent-safe from NEW
