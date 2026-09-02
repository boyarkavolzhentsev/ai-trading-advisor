"""Stage 10A read-only MT5 adapter.

The ONLY module in this repository allowed to import ``MetaTrader5`` or hold
a reference to one of its raw objects. Every raw tuple/object/integer
constant is normalized into an ``app.core.models.mt5_runtime``/
``app.core.enums.mt5_runtime`` value before it ever leaves a method here -
callers, including every pure Stage 10B-E consumer, only ever see
``MT5RuntimeStatus``/``MT5AccountFacts``/``AccountPositionMode``.

Construction performs no I/O: it only stores configuration. ``initialize()``
is the one method that performs the actual ``MetaTrader5.initialize(...)``
call (lazily imported, so ``import app.mt5.client`` itself never requires
the package to be installed). Every legitimate broker/terminal/account
condition becomes a typed ``MT5ConnectivityState`` - never an exception, and
never a raw ``MetaTrader5`` object or error tuple. Only a genuine
caller-contract violation (an initialized-only method called before
``initialize()`` succeeds, or after ``shutdown()``) raises
``MT5NotInitializedError``.

No reconnect loop, no background polling, no autonomous retry: every method
here does exactly one synchronous read and returns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.models.mt5_runtime import MT5AccountFacts, MT5Credentials, MT5RuntimeStatus
from app.mt5.errors import MT5NotInitializedError


def _stringify_last_error(mt5_module: Any) -> str | None:
    """A sanitized, stringified ``last_error()`` - never the raw tuple
    ``MetaTrader5`` returns."""
    try:
        error = mt5_module.last_error()
    except Exception:
        return None
    if not error:
        return None
    return str(error)


def _normalize_margin_mode(raw_margin_mode: int, mt5_module: Any) -> AccountPositionMode:
    """Map the raw ``ACCOUNT_MARGIN_MODE_*`` integer constant onto
    ``AccountPositionMode`` - see that enum's own docstring for the exact
    three-raw-values-to-two-normalized-values rationale. An unrecognized
    future raw value maps to ``UNKNOWN``, never raises."""
    mapping = {
        getattr(mt5_module, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", object()): AccountPositionMode.HEDGING,
        getattr(mt5_module, "ACCOUNT_MARGIN_MODE_RETAIL_NETTING", object()): AccountPositionMode.NETTING,
        getattr(mt5_module, "ACCOUNT_MARGIN_MODE_EXCHANGE", object()): AccountPositionMode.NETTING,
    }
    return mapping.get(raw_margin_mode, AccountPositionMode.UNKNOWN)


class MT5Client:
    """Impure Stage 10A adapter implementing ``MT5ClientProtocol``.

    ``mt5_module`` is a test-only injection seam: production callers never
    pass it, leaving ``initialize()`` to lazily ``import MetaTrader5``
    itself; a fake/protocol-shaped stand-in may be passed directly so
    Stage 10A's own tests never require the real package installed.
    """

    def __init__(
        self,
        *,
        path: str | None = None,
        timeout: int = 60_000,
        credentials: MT5Credentials | None = None,
        mt5_module: Any | None = None,
    ) -> None:
        self._path = path
        self._timeout = timeout
        self._credentials = credentials
        self._injected_mt5_module = mt5_module
        self._mt5: Any | None = None
        self._initialized = False

    def initialize(self) -> MT5RuntimeStatus:
        mt5 = self._injected_mt5_module
        if mt5 is None:
            import MetaTrader5 as mt5_package  # lazy: only this line ever requires the package installed

            mt5 = mt5_package
        self._mt5 = mt5

        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._path is not None:
            kwargs["path"] = self._path

        credentials_supplied = self._credentials is not None and self._credentials.login is not None
        if credentials_supplied:
            assert self._credentials is not None
            kwargs["login"] = self._credentials.login
            if self._credentials.password is not None:
                kwargs["password"] = self._credentials.password.get_secret_value()
            if self._credentials.server is not None:
                kwargs["server"] = self._credentials.server

        succeeded = bool(mt5.initialize(**kwargs))
        as_of = datetime.now(UTC)

        if not succeeded:
            self._initialized = False
            reason = _stringify_last_error(mt5)
            state = MT5ConnectivityState.LOGIN_FAILED if credentials_supplied else MT5ConnectivityState.INITIALIZATION_FAILED
            return MT5RuntimeStatus(as_of=as_of, state=state, reason=reason)

        self._initialized = True
        return self._current_status()

    def runtime_status(self) -> MT5RuntimeStatus:
        if not self._initialized or self._mt5 is None:
            raise MT5NotInitializedError("runtime_status() called before a successful initialize()")
        return self._current_status()

    def account_facts(self) -> MT5AccountFacts | None:
        if not self._initialized or self._mt5 is None:
            raise MT5NotInitializedError("account_facts() called before a successful initialize()")

        status = self._current_status()
        if status.state is not MT5ConnectivityState.AVAILABLE:
            return None

        account_info = self._mt5.account_info()
        if account_info is None:
            return None

        margin_level = Decimal(str(account_info.margin_level)) if account_info.margin_level else None
        return MT5AccountFacts(
            as_of=status.as_of,
            equity=Decimal(str(account_info.equity)),
            balance=Decimal(str(account_info.balance)),
            margin=Decimal(str(account_info.margin)),
            margin_free=Decimal(str(account_info.margin_free)),
            margin_level=margin_level,
            currency=account_info.currency,
            trade_allowed=bool(account_info.trade_allowed),
            trade_expert=bool(account_info.trade_expert),
            margin_mode=_normalize_margin_mode(account_info.margin_mode, self._mt5),
            floating_pnl=Decimal(str(account_info.profit)),
        )

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
        self._initialized = False

    def _current_status(self) -> MT5RuntimeStatus:
        mt5 = self._mt5
        assert mt5 is not None
        as_of = datetime.now(UTC)

        terminal_info = mt5.terminal_info()
        if terminal_info is None or not terminal_info.connected:
            return MT5RuntimeStatus(
                as_of=as_of, state=MT5ConnectivityState.TERMINAL_UNAVAILABLE, reason=_stringify_last_error(mt5)
            )

        account_info = mt5.account_info()
        if account_info is None:
            return MT5RuntimeStatus(
                as_of=as_of, state=MT5ConnectivityState.ACCOUNT_UNAVAILABLE, reason=_stringify_last_error(mt5)
            )

        return MT5RuntimeStatus(as_of=as_of, state=MT5ConnectivityState.AVAILABLE)


__all__ = ["MT5Client"]
