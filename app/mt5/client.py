"""Stage 10A/10B/10C/10D read-only MT5 adapter.

The ONLY module in this repository allowed to import ``MetaTrader5`` or hold
a reference to one of its raw objects. Every raw tuple/object/integer
constant is normalized into an ``app.core.models.mt5_runtime``/
``app.core.models.mt5_position``/``app.core.models.mt5_symbol``/
``app.core.models.mt5_history`` value before it ever leaves a method here -
callers, including every pure Stage 10D-E consumer, only ever see the
normalized domain models.

Construction performs no I/O: it only stores configuration. ``initialize()``
is the one method that performs the actual ``MetaTrader5.initialize(...)``
call (lazily imported, so ``import app.mt5.client`` itself never requires
the package to be installed). Every legitimate broker/terminal/account
condition becomes a typed state - never an exception, and never a raw
``MetaTrader5`` object or error tuple. Only a genuine caller-contract
violation (an initialized-only method called before ``initialize()``
succeeds, or after ``shutdown()``) raises ``MT5NotInitializedError``.

No reconnect loop, no background polling, no autonomous retry: every method
here does exactly one synchronous read and returns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.enums.order import OrderSide
from app.core.models.base import Timestamp
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5AccountFacts, MT5Credentials, MT5RuntimeStatus
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.mt5.errors import MT5NotInitializedError
from app.mt5.history import MT5HistoryReadStatus
from app.mt5.risk import MT5PositionsReadStatus


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


def _normalize_position_side(raw_type: int, mt5_module: Any) -> OrderSide | None:
    """Map the raw ``POSITION_TYPE_*`` integer constant onto ``OrderSide``.
    Unlike margin mode, an unrecognized value has no safe fallback: getting
    BUY/SELL wrong would silently misapply the open-risk formula in the
    wrong direction - so this returns ``None`` (never a fabricated side),
    and the caller (``positions()``) fails the whole read closed."""
    mapping = {
        getattr(mt5_module, "POSITION_TYPE_BUY", object()): OrderSide.BUY,
        getattr(mt5_module, "POSITION_TYPE_SELL", object()): OrderSide.SELL,
    }
    return mapping.get(raw_type)


def _normalize_trade_mode(raw_trade_mode: int, mt5_module: Any) -> MT5SymbolTradeMode:
    """Map the raw ``SYMBOL_TRADE_MODE_*`` integer constant onto
    ``MT5SymbolTradeMode``. An unrecognized future raw value maps to
    ``UNKNOWN``, never raises - ``app.mt5.sizing`` treats ``UNKNOWN`` as
    non-tradable in either direction."""
    mapping = {
        getattr(mt5_module, "SYMBOL_TRADE_MODE_DISABLED", object()): MT5SymbolTradeMode.DISABLED,
        getattr(mt5_module, "SYMBOL_TRADE_MODE_LONGONLY", object()): MT5SymbolTradeMode.LONG_ONLY,
        getattr(mt5_module, "SYMBOL_TRADE_MODE_SHORTONLY", object()): MT5SymbolTradeMode.SHORT_ONLY,
        getattr(mt5_module, "SYMBOL_TRADE_MODE_CLOSEONLY", object()): MT5SymbolTradeMode.CLOSE_ONLY,
        getattr(mt5_module, "SYMBOL_TRADE_MODE_FULL", object()): MT5SymbolTradeMode.FULL,
    }
    return mapping.get(raw_trade_mode, MT5SymbolTradeMode.UNKNOWN)


_NON_TRADING_DEAL_TYPE_NAMES: tuple[str, ...] = (
    "DEAL_TYPE_BALANCE",
    "DEAL_TYPE_CREDIT",
    "DEAL_TYPE_CHARGE",
    "DEAL_TYPE_CORRECTION",
    "DEAL_TYPE_BONUS",
    "DEAL_TYPE_COMMISSION",
    "DEAL_TYPE_COMMISSION_DAILY",
    "DEAL_TYPE_COMMISSION_MONTHLY",
    "DEAL_TYPE_COMMISSION_AGENT_DAILY",
    "DEAL_TYPE_COMMISSION_AGENT_MONTHLY",
    "DEAL_TYPE_INTEREST",
    "DEAL_TYPE_BUY_CANCELED",
    "DEAL_TYPE_SELL_CANCELED",
    "DEAL_TYPE_DIVIDEND",
    "DEAL_TYPE_DIVIDEND_FRANKED",
    "DEAL_TYPE_TAX",
)
"""Every known non-trading/account-operation raw ``DEAL_TYPE_*`` name -
none is individually distinguished by ``MT5DealType`` because none
individually matters for V1 (see that enum's own docstring)."""


def _normalize_deal_type(raw_type: int, mt5_module: Any) -> MT5DealType:
    """Map the raw ``DEAL_TYPE_*`` integer constant onto ``MT5DealType``.
    Every known non-trading/account-operation raw type collapses onto
    ``NON_TRADING``; an unrecognized future raw value maps to ``UNKNOWN`` -
    never raises, mirroring ``_normalize_trade_mode``'s permissive style
    (the safety judgment on ``UNKNOWN`` is made downstream, by
    ``app.mt5.history``, never here)."""
    mapping: dict[Any, MT5DealType] = {
        getattr(mt5_module, "DEAL_TYPE_BUY", object()): MT5DealType.BUY,
        getattr(mt5_module, "DEAL_TYPE_SELL", object()): MT5DealType.SELL,
    }
    for name in _NON_TRADING_DEAL_TYPE_NAMES:
        mapping[getattr(mt5_module, name, object())] = MT5DealType.NON_TRADING
    return mapping.get(raw_type, MT5DealType.UNKNOWN)


def _normalize_deal_entry(raw_entry: int, mt5_module: Any) -> MT5DealEntry:
    """Map the raw ``DEAL_ENTRY_*`` integer constant onto ``MT5DealEntry``.
    An unrecognized future raw value maps to ``UNKNOWN`` - never raises,
    mirroring ``_normalize_deal_type``."""
    mapping = {
        getattr(mt5_module, "DEAL_ENTRY_IN", object()): MT5DealEntry.IN,
        getattr(mt5_module, "DEAL_ENTRY_OUT", object()): MT5DealEntry.OUT,
        getattr(mt5_module, "DEAL_ENTRY_INOUT", object()): MT5DealEntry.INOUT,
        getattr(mt5_module, "DEAL_ENTRY_OUT_BY", object()): MT5DealEntry.OUT_BY,
    }
    return mapping.get(raw_entry, MT5DealEntry.UNKNOWN)


def _normalize_deal_timestamp(time_msc: int) -> Timestamp | None:
    """Deterministic epoch-millisecond -> aware UTC datetime conversion.
    Returns ``None`` for a non-positive/unset ``time_msc`` (MT5's own "no
    value" sentinel, mirroring ``MT5Position.stop_loss``'s ``sl == 0.0``
    treatment one layer over) or one that fails to convert - the caller
    (``history_deals()``) fails the whole read closed rather than silently
    dropping the one malformed deal."""
    if not time_msc or time_msc <= 0:
        return None
    seconds, milliseconds = divmod(int(time_msc), 1000)
    try:
        return datetime.fromtimestamp(seconds, tz=UTC) + timedelta(milliseconds=milliseconds)
    except (OSError, OverflowError, ValueError):
        return None


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

    def positions(self) -> tuple[MT5PositionsReadStatus, tuple[MT5Position, ...]]:
        if not self._initialized or self._mt5 is None:
            raise MT5NotInitializedError("positions() called before a successful initialize()")

        status = self._current_status()
        if status.state is not MT5ConnectivityState.AVAILABLE:
            return "UNAVAILABLE", ()

        raw_positions = self._mt5.positions_get()
        if raw_positions is None:
            return "UNAVAILABLE", ()
        if not raw_positions:
            return "OK", ()

        as_of = datetime.now(UTC)
        normalized: list[MT5Position] = []
        for raw_position in raw_positions:
            side = _normalize_position_side(raw_position.type, self._mt5)
            if side is None:
                return "UNMAPPABLE_POSITION_SIDE", ()

            stop_loss = Decimal(str(raw_position.sl)) if raw_position.sl else None
            normalized.append(
                MT5Position(
                    as_of=as_of,
                    ticket=int(raw_position.ticket),
                    symbol=raw_position.symbol,
                    side=side,
                    volume=Decimal(str(raw_position.volume)),
                    price_open=Decimal(str(raw_position.price_open)),
                    price_current=Decimal(str(raw_position.price_current)),
                    stop_loss=stop_loss,
                )
            )
        return "OK", tuple(normalized)

    def symbol_facts(self, symbol: str) -> MT5SymbolFacts | None:
        if not self._initialized or self._mt5 is None:
            raise MT5NotInitializedError("symbol_facts() called before a successful initialize()")

        status = self._current_status()
        if status.state is not MT5ConnectivityState.AVAILABLE:
            return None

        symbol_info = self._mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return MT5SymbolFacts(
            as_of=status.as_of,
            symbol=symbol,
            trade_tick_size=Decimal(str(symbol_info.trade_tick_size)),
            trade_tick_value_loss=Decimal(str(symbol_info.trade_tick_value_loss)),
            volume_min=Decimal(str(symbol_info.volume_min)),
            volume_max=Decimal(str(symbol_info.volume_max)),
            volume_step=Decimal(str(symbol_info.volume_step)),
            trade_stops_level=int(symbol_info.trade_stops_level),
            trade_mode=_normalize_trade_mode(symbol_info.trade_mode, self._mt5),
            bid=Decimal(str(tick.bid)),
            ask=Decimal(str(tick.ask)),
        )

    def history_deals(self, *, start: Timestamp, end: Timestamp) -> tuple[MT5HistoryReadStatus, tuple[MT5Deal, ...]]:
        if not self._initialized or self._mt5 is None:
            raise MT5NotInitializedError("history_deals() called before a successful initialize()")

        status = self._current_status()
        if status.state is not MT5ConnectivityState.AVAILABLE:
            return "UNAVAILABLE", ()

        raw_deals = self._mt5.history_deals_get(start, end)
        if raw_deals is None:
            return "UNAVAILABLE", ()
        if not raw_deals:
            return "OK", ()

        normalized: list[MT5Deal] = []
        for raw_deal in raw_deals:
            deal_time = _normalize_deal_timestamp(raw_deal.time_msc)
            if deal_time is None:
                return "MALFORMED_TIMESTAMP", ()

            normalized.append(
                MT5Deal(
                    ticket=int(raw_deal.ticket),
                    order=int(raw_deal.order),
                    position_id=int(raw_deal.position_id),
                    time=deal_time,
                    symbol=raw_deal.symbol or None,
                    deal_type=_normalize_deal_type(raw_deal.type, self._mt5),
                    entry=_normalize_deal_entry(raw_deal.entry, self._mt5),
                    volume=Decimal(str(raw_deal.volume)),
                    price=Decimal(str(raw_deal.price)),
                    profit=Decimal(str(raw_deal.profit)),
                    commission=Decimal(str(raw_deal.commission)),
                    swap=Decimal(str(raw_deal.swap)),
                    fee=Decimal(str(getattr(raw_deal, "fee", 0))),
                )
            )
        return "OK", tuple(normalized)

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
