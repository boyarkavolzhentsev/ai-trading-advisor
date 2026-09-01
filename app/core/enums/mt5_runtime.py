"""Stage 10A MT5 runtime/connectivity enums - deterministic broker-runtime
vocabulary only.

No member here means BUY/SELL/LONG/SHORT/ENTER/EXIT/HOLD, a qualitative
market judgment, or a trade/execution action. Every value describes either
the coarse read-only connectivity state of the local MT5 terminal/account, or
the normalized account margining regime - never an order, position, or
history fact (those belong to a later Stage 10 sub-stage).
"""

from __future__ import annotations

from enum import StrEnum


class MT5ConnectivityState(StrEnum):
    """Coarse, mutually exclusive read-only connectivity state of the local
    MT5 terminal/account, re-derived on every ``runtime_status()`` call.

    Exactly one state applies at a time; each has exactly one deterministic
    trigger (see ``app.mt5.client``). Only ``AVAILABLE`` permits
    ``account_facts()`` to return a populated fact and only ``AVAILABLE``
    permits any downstream trading-cycle work to proceed. ``STALE`` is
    deliberately not a member here: staleness is a caller-side comparison of
    ``MT5RuntimeStatus.as_of`` against a caller-chosen threshold, not a fact
    the client itself can determine.
    """

    AVAILABLE = "AVAILABLE"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
    LOGIN_FAILED = "LOGIN_FAILED"
    TERMINAL_UNAVAILABLE = "TERMINAL_UNAVAILABLE"
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"


class AccountPositionMode(StrEnum):
    """Normalized account margining regime, mapped from the raw MT5
    ``ACCOUNT_MARGIN_MODE_*`` integer constant by ``app.mt5.client`` - never
    exposed as a raw integer outside that module.

    The real MT5 API reports three raw values, not two:
    ``ACCOUNT_MARGIN_MODE_RETAIL_HEDGING``, ``ACCOUNT_MARGIN_MODE_RETAIL_
    NETTING`` and ``ACCOUNT_MARGIN_MODE_EXCHANGE``. Both retail-netting and
    exchange-margined accounts net same-symbol positions per their own rule
    set - a distinction no Stage 10 V1 consumer needs - so both map onto
    ``NETTING``, only ``RETAIL_HEDGING`` maps onto ``HEDGING``, and any
    unrecognized future raw value maps onto ``UNKNOWN`` rather than raising.
    """

    HEDGING = "HEDGING"
    NETTING = "NETTING"
    UNKNOWN = "UNKNOWN"


__all__ = [
    "AccountPositionMode",
    "MT5ConnectivityState",
]
