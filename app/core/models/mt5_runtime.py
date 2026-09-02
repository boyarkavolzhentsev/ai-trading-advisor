"""Stage 10A MT5 read-only adapter foundation output contracts.

Normalizes exactly two facts the impure ``app.mt5.client`` adapter produces
on every cycle - the coarse connectivity state of the local terminal/account,
and (only when available) the account's own monetary/margining facts - plus
the one caller-supplied fact the adapter needs to connect
(``MT5Credentials``). No raw MetaTrader5 tuple, object, or integer constant
is ever carried by these models: ``app.mt5.client`` is the only file that
ever sees one, and every value here is already normalized before it exists
as one of these models (see ``app.core.enums.mt5_runtime.AccountPositionMode``
for the one raw-integer mapping performed at that boundary).

These are deliberately not ``AccountRiskSnapshot`` (Stage 7's own model,
untouched): ``MT5AccountFacts`` is a raw-but-normalized one-``account_info()``
-call snapshot: how it becomes an ``AccountRiskSnapshot`` (rollover-equity
freezing, realized/floating PnL derivation) is a later Stage 10 sub-stage's
job, not 10A's.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, SecretStr, model_validator

from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.models.base import DomainModel, Money, Timestamp


class MT5RuntimeStatus(DomainModel):
    """Coarse, point-in-time connectivity fact for the local MT5
    terminal/account.

    ``reason`` is optional even for a non-``AVAILABLE`` state (MT5 does not
    always surface a specific ``last_error``), but must be absent when
    ``state`` is ``AVAILABLE`` - mirroring every Stage 7-9 result's own
    "reason(s) present iff not the success case" discipline.
    """

    as_of: Timestamp
    state: MT5ConnectivityState
    reason: Annotated[str, Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _validate_reason_absent_when_available(self) -> Self:
        if self.state is MT5ConnectivityState.AVAILABLE and self.reason is not None:
            raise ValueError("AVAILABLE must not carry a reason")
        return self


class MT5AccountFacts(DomainModel):
    """Normalized, one-``account_info()``-call snapshot of account/terminal
    facts - never account identity.

    ``trade_allowed`` (terminal-level "AutoTrading" permission) and
    ``trade_expert`` (account-level API/EA trading permission) are carried
    as facts only in Stage 10A: neither gates ``MT5ConnectivityState``, and
    neither is enforced as a policy here - a later stage decides whether
    either should affect recommendation output. ``margin_level`` is ``None``
    when MT5 reports it undefined (no open exposure) - never a fabricated
    zero. ``floating_pnl`` (Stage 10B amendment) is the account-level
    floating profit/loss across all open positions as MT5 itself reports it
    (``account_info().profit``) - signed, never clamped, never defaulted to
    zero; a flat account with no open exposure legitimately reports an
    actual ``0``, which is not the same as an unavailable fact (unlike
    ``margin_level``, MT5 documents no undefined state for this field, so it
    is populated unconditionally whenever ``account_info()`` itself is
    available). Deliberately excludes account login, account number, server
    identity and password: no Stage 10A-E responsibility audited so far
    needs account identity (matching is always by ``trade_id``/ticket), so
    none is carried.
    """

    as_of: Timestamp
    equity: Money
    balance: Money
    margin: Money
    margin_free: Money
    margin_level: Annotated[Decimal, Field(ge=0)] | None = None
    currency: Annotated[str, Field(min_length=1)]
    trade_allowed: bool
    trade_expert: bool
    margin_mode: AccountPositionMode
    floating_pnl: Decimal


class MT5Credentials(DomainModel):
    """Optional explicit login transport for ``app.mt5.client``.

    Preferred V1 mode is to supply none of these and use whatever account
    the local terminal is already authenticated as; explicit credentials
    remain supported for a headless/automated terminal. ``password`` is a
    ``SecretStr`` so it can never appear in a ``repr()``/``str()``/log of
    this model - callers must call ``.get_secret_value()`` explicitly to
    read it, exactly once, at the ``app.mt5.client`` boundary.
    """

    login: Annotated[int, Field(gt=0)] | None = None
    password: SecretStr | None = None
    server: Annotated[str, Field(min_length=1)] | None = None


__all__ = ["MT5AccountFacts", "MT5Credentials", "MT5RuntimeStatus"]
