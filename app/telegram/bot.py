"""Telegram bot factory and production runner.

``build_bot`` is the primary testability seam (mirrors ``app.api.main.
create_app``'s own "no env read, no network, pure construction" discipline):
it never reads an environment variable and never contacts Telegram - it only
wires an already-constructed ``ApplicationAdvisoryService``/symbol/allowlist
onto a ``telegram.ext.Application`` object. ``run()`` is the sole production
entrypoint, combining ``app.bootstrap.production``'s existing factories with
this package's own Telegram-specific config (``app.telegram.config``) -
never duplicating production config parsing, never constructing a second
``ProductionAdvisoryComposer``.
"""

from __future__ import annotations

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.application.advisory_service import ApplicationAdvisoryService
from app.bootstrap.production import build_production_advisory_config_from_env, build_production_advisory_service
from app.telegram.config import build_telegram_allowlist_from_env, build_telegram_bot_token_from_env
from app.telegram.handlers import handle_help, handle_non_command, handle_signal, handle_start, handle_status


def build_bot(
    *,
    token: str,
    service: ApplicationAdvisoryService,
    symbol: str,
    allowlist: frozenset[int],
) -> Application:
    """Pure offline construction - no environment read, no Telegram network
    call. Registers exactly four command handlers plus one non-command
    handler, all private-chat-only. Never calls ``.initialize()``/
    ``.start()``/``.run_polling()`` itself."""

    async def post_init(app: Application) -> None:
        await service.startup()
        app.bot_data["advisory_service"] = service
        app.bot_data["symbol"] = symbol
        app.bot_data["allowlist"] = allowlist

    async def post_shutdown(app: Application) -> None:
        """Called unconditionally, even when ``post_init`` (and therefore
        ``service.startup()``) raised - traced directly from the installed
        python-telegram-bot 22.8 source
        (``telegram/ext/_application.py::Application.__run``): its
        ``finally:`` block unconditionally awaits ``self.shutdown()``/
        ``self.post_shutdown(self)`` regardless of whether the preceding
        ``try`` block's ``post_init`` call raised (Python's own ``finally``
        semantics - it runs even while an uncaught exception is
        propagating). No ``started`` boolean guard is added here: calling
        ``service.shutdown()`` on a service whose ``startup()`` never
        completed is proven safe by
        ``app.production_advisory.composer.ProductionAdvisoryComposer.shutdown``'s
        own explicit, documented contract ("Always idempotent, including
        from NEW... shutdown never raises") - see the approved pre-commit
        lifecycle review, "2. SERVICE SHUTDOWN AFTER FAILED STARTUP", and
        ``tests/test_telegram_lifecycle.py::
        test_post_shutdown_after_failed_startup_is_safe_with_real_composer``
        for the real (non-mocked) proof. Adding a guard here would be an
        unnecessary second lifecycle state machine layered on top of an
        already-safe one."""
        await service.shutdown()

    application = Application.builder().token(token).post_init(post_init).post_shutdown(post_shutdown).build()

    private_only = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", handle_start, filters=private_only))
    application.add_handler(CommandHandler("help", handle_help, filters=private_only))
    application.add_handler(CommandHandler("status", handle_status, filters=private_only))
    application.add_handler(CommandHandler("signal", handle_signal, filters=private_only))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_non_command))

    return application


def run() -> None:
    """Production-only entrypoint - never executed at import time. Long
    polling only, no webhook, no FastAPI call, no remote deployment.

    Real PTB 22.8 execution order inside ``application.run_polling()``
    (confirmed directly from the installed source, ``Application.
    run_polling``'s own docstring plus ``Application.__run``): ``initialize()``
    -> ``post_init`` -> ``Updater.start_polling()`` -> ``start()`` -> ... ->
    ``Updater.stop()`` -> ``stop()`` -> ``post_stop`` -> ``shutdown()`` ->
    ``post_shutdown``. ``Application.initialize()`` calls ``Bot.initialize()``,
    which itself calls ``Bot.get_me()`` - a real Telegram Bot API network
    call used to validate the token - so Telegram IS contacted before our
    own ``post_init``/``service.startup()`` ever runs. This is normal,
    expected PTB behavior (token validation happens first) and does not
    conflict with this module's design: nothing here depends on
    ``service.startup()`` running before Telegram itself is reachable."""
    token = build_telegram_bot_token_from_env()
    allowlist = build_telegram_allowlist_from_env()
    config = build_production_advisory_config_from_env()
    service = build_production_advisory_service()
    application = build_bot(token=token, service=service, symbol=config.symbol_mapping.logical_symbol, allowlist=allowlist)
    application.run_polling()


if __name__ == "__main__":
    run()


__all__ = ["build_bot", "run"]
