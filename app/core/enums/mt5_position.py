"""Stage 10C existing-open-position open-risk vocabulary.

Describes only the outcome/reason space of the account-wide
``current_open_risk_to_stop`` assessment - never a trade recommendation, an
execution action, or MT5 connectivity/rollover state (those remain
``MT5ConnectivityState``'s and ``MT5RolloverOutcome``'s exclusive
vocabularies, never duplicated here).
"""

from __future__ import annotations

from enum import StrEnum


class MT5OpenRiskOutcome(StrEnum):
    """Coarse result of one account-wide open-risk assessment.

    ``READY`` means every open position was safely assessable (including
    positions that are protected and so contribute ``0``); ``BLOCKED`` means
    at least one position could not be safely assessed, and the whole
    assessment fails closed - no partial monetary sum is ever produced.
    """

    READY = "READY"
    BLOCKED = "BLOCKED"


class MT5OpenRiskBlockReason(StrEnum):
    """Why one or more open positions could not be safely assessed.

    ``NO_PROTECTIVE_STOP`` fires for any position with no stop, regardless of
    its entry/current relationship. ``INVALID_CURRENT_PRICE``/
    ``INVALID_TICK_ECONOMICS``/``SYMBOL_UNAVAILABLE`` only ever apply to a
    position that is NOT protected under the entry/stop classification (see
    ``app.mt5.risk``) - a protected position never needs its current price,
    tick economics, or symbol facts validated at all, since its contribution
    is already safely bounded to zero by the entry/stop relationship alone.
    """

    NO_PROTECTIVE_STOP = "NO_PROTECTIVE_STOP"
    INVALID_CURRENT_PRICE = "INVALID_CURRENT_PRICE"
    INVALID_TICK_ECONOMICS = "INVALID_TICK_ECONOMICS"
    SYMBOL_UNAVAILABLE = "SYMBOL_UNAVAILABLE"


__all__ = [
    "MT5OpenRiskBlockReason",
    "MT5OpenRiskOutcome",
]
