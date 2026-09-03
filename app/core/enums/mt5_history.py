"""Stage 10D MT5 deal-history normalization vocabulary.

Describes only the raw-broker-deal classification space needed to compute
``realized_daily_pnl`` deterministically - never a trade recommendation, an
execution action, or MT5 connectivity/rollover/open-position state (those
remain ``MT5ConnectivityState``'s, ``MT5RolloverOutcome``'s and
``MT5OpenRiskOutcome``'s exclusive vocabularies, never duplicated here).
"""

from __future__ import annotations

from enum import StrEnum


class MT5DealType(StrEnum):
    """Normalized classification of one raw MT5 ``DEAL_TYPE_*`` constant.

    ``BUY``/``SELL`` are the only types that can ever contribute to
    ``realized_daily_pnl``. Every known non-trading/account-operation raw
    type (balance, credit, charge, correction, bonus, commission-standalone,
    interest, canceled, dividend, tax) collapses onto ``NON_TRADING`` - none
    is individually distinguished because none individually matters for V1:
    all are uniformly excluded from realized trading PnL. ``UNKNOWN`` is an
    unrecognized future raw value - unlike ``NON_TRADING``, it is not
    confirmed safe to exclude, so ``app.mt5.history`` fails the whole
    assessment closed whenever it is encountered on a deal that would
    otherwise need classifying, rather than silently excluding it.
    """

    BUY = "BUY"
    SELL = "SELL"
    NON_TRADING = "NON_TRADING"
    UNKNOWN = "UNKNOWN"


class MT5DealEntry(StrEnum):
    """Normalized classification of one raw MT5 ``DEAL_ENTRY_*`` constant.

    Only meaningful for ``MT5DealType.BUY``/``SELL`` deals - irrelevant for
    ``NON_TRADING`` deals, which are excluded by type alone before entry is
    ever consulted. ``IN`` opens/adds exposure only. ``OUT``/``INOUT``
    reduce or close exposure and carry realized economics. ``OUT_BY``
    (close-by an opposite position) is a recognized but deliberately
    unsupported V1 pattern - see ``app.mt5.history``. ``UNKNOWN`` is an
    unrecognized future raw value and, like ``MT5DealType.UNKNOWN``, always
    fails the whole assessment closed rather than being silently ignored.
    """

    IN = "IN"
    OUT = "OUT"
    INOUT = "INOUT"
    OUT_BY = "OUT_BY"
    UNKNOWN = "UNKNOWN"


class MT5RealizedPnLOutcome(StrEnum):
    """Coarse result of one broker-trading-day realized-PnL assessment.

    Mirrors ``MT5OpenRiskOutcome`` exactly: ``READY`` means every deal
    relevant to the assessment was safely classifiable (including a
    confirmed-empty qualifying set, which is a genuine ``Decimal("0")``);
    ``BLOCKED`` means at least one deal could not be safely classified, and
    the whole assessment fails closed - no partial sum is ever produced.
    """

    READY = "READY"
    BLOCKED = "BLOCKED"


class MT5RealizedPnLBlockReason(StrEnum):
    """Why one or more deals could not be safely folded into
    ``realized_daily_pnl``.

    ``MALFORMED_TIMESTAMP`` fires for any deal (trading or non-trading)
    whose ``time`` cannot be trusted enough to even test against the
    trading-day window. ``UNMAPPABLE_DEAL_TYPE``/``UNMAPPABLE_DEAL_ENTRY``
    fire only for a ``BUY``/``SELL`` deal whose raw type/entry was not one
    of the known values. ``UNSUPPORTED_OUT_BY`` fires for any ``BUY``/
    ``SELL`` deal whose entry is ``OUT_BY`` - see ``app.mt5.history`` for
    why close-by economics are never computed in V1.
    """

    MALFORMED_TIMESTAMP = "MALFORMED_TIMESTAMP"
    UNMAPPABLE_DEAL_TYPE = "UNMAPPABLE_DEAL_TYPE"
    UNMAPPABLE_DEAL_ENTRY = "UNMAPPABLE_DEAL_ENTRY"
    UNSUPPORTED_OUT_BY = "UNSUPPORTED_OUT_BY"


__all__ = [
    "MT5DealEntry",
    "MT5DealType",
    "MT5RealizedPnLBlockReason",
    "MT5RealizedPnLOutcome",
]
