"""Stage 10D pure broker-trading-day realized-PnL assessment.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock - a deterministic, synchronous function of its explicit
arguments only (already-normalized deals and an explicit, already-derived
trading-day interval). Mirrors ``app.mt5.risk`` one architectural layer over:
expected assessment states are typed return values, never exceptions.

The impure boundary (``app.mt5.client``, and whatever future caller derives
the trading-day interval via ``app.mt5.rollover.trading_day_interval`` and
obtains ``as_of``) is responsible for reading deal history and obtaining the
window - this module never gathers any of them itself.

Formula (see the approved Stage 10D design)::

    realized_daily_pnl =
        SUM(commission + fee) for every qualifying BUY/SELL deal in the window
      + SUM(profit + swap) for qualifying BUY/SELL deals whose entry is OUT or INOUT

Commission/fee are summed across every trading deal (the opening leg
included) because they immediately reduce balance the instant a broker posts
them, regardless of a broker's own open/close commission-timing convention -
never "floating," so omitting an opening leg's commission would silently
overstate available daily-loss capacity. Profit/swap are summed only across
closing-type deals (``OUT``/``INOUT``): MT5 reports profit as structurally
zero on an opening (``IN``) deal, and this repository's own Stage 10C design
already treats an open position's accrued swap as reflected account-level in
``floating_pnl`` (see ``MT5Position``'s docstring) - counting it again here
on an opening deal would double count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.models.base import Timestamp
from app.core.models.mt5_history import MT5Deal, MT5RealizedDailyPnLAssessment

MT5HistoryReadStatus = Literal["OK", "UNAVAILABLE", "MALFORMED_TIMESTAMP"]
"""What ``MT5Client.history_deals()`` observed. Defined here (the pure
module) rather than in the impure ``app.mt5.client`` so this module never
depends on its own impure counterpart - ``client.py`` imports this alias
instead, mirroring ``app.mt5.rollover.PersistedStateReadStatus``/``app.mt5.
risk.MT5PositionsReadStatus``'s identical precedent. ``MALFORMED_TIMESTAMP``
mirrors ``MT5PositionsReadStatus``'s own ``"UNMAPPABLE_POSITION_SIDE"``: a
single raw deal that cannot be safely normalized fails the whole read, never
a silently-dropped deal."""

_REASON_ORDER: tuple[MT5RealizedPnLBlockReason, ...] = tuple(MT5RealizedPnLBlockReason)
"""A locally-owned copy of the canonical reason order - not imported from
``app.core.models.mt5_history`` (whose own model validator independently
re-derives the identical order to self-validate ``MT5RealizedDailyPnLAssessment``),
mirroring the Stage 5A/6A/6C/7/8/9/10B/10C precedent of the operational
component and the result model's self-validation maintaining independent
copies of the same primitive rather than cross-importing one from the
other."""

_EPOCH: Timestamp = datetime(1970, 1, 1, tzinfo=UTC)
"""Real MT5 deals can never legitimately predate the Unix epoch - a deal
whose normalized ``time`` is at or before it is MT5's own "unset" sentinel
having survived normalization as a real (if implausible) datetime, not a
genuine historical fact. Checked unconditionally, before window filtering:
a timestamp that cannot be trusted this far cannot be trusted enough to
compare against the window either."""


def classify_trading_deal(deal: MT5Deal) -> tuple[Decimal | None, MT5RealizedPnLBlockReason | None]:
    """One ``BUY``/``SELL`` deal's contribution, or the reason it cannot be
    safely folded into realized PnL. Returns ``(value, None)`` on success,
    ``(None, reason)`` on failure - never both, never neither.

    Exported (Stage 10E amendment) so a position-lifecycle-scoped PnL
    aggregation (``app.mt5.tracker``) can reuse this exact per-deal
    classification rather than duplicating it - the caller decides which
    deals to feed it (a trading-day window here, a ``position_id`` lifecycle
    there); this function itself remains window-agnostic and unchanged."""
    if deal.entry is MT5DealEntry.IN:
        return deal.commission + deal.fee, None

    if deal.entry in (MT5DealEntry.OUT, MT5DealEntry.INOUT):
        return deal.commission + deal.fee + deal.profit + deal.swap, None

    if deal.entry is MT5DealEntry.OUT_BY:
        return None, MT5RealizedPnLBlockReason.UNSUPPORTED_OUT_BY

    return None, MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_ENTRY  # MT5DealEntry.UNKNOWN


def compute_realized_daily_pnl(
    *,
    as_of: Timestamp,
    trading_day_key: str,
    deals: tuple[MT5Deal, ...],
    window_start: Timestamp,
    window_end: Timestamp,
) -> MT5RealizedDailyPnLAssessment:
    """The broker-trading-day aggregation: ``READY`` only if every deal
    considered is safely classifiable; if ANY deal is unsafe, the whole
    assessment is ``BLOCKED`` - no partial sum, no silently-excluded ticket.

    ``[window_start, window_end)`` is half-open: a deal whose normalized
    ``time`` falls exactly on ``window_start`` belongs to this trading day;
    one falling exactly on ``window_end`` belongs to the next.
    """
    contributions: list[Decimal] = []
    blocked_reason_set: set[MT5RealizedPnLBlockReason] = set()
    unsafe_tickets: list[int] = []

    for deal in deals:
        if deal.time <= _EPOCH:
            blocked_reason_set.add(MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP)
            unsafe_tickets.append(deal.ticket)
            continue

        if not (window_start <= deal.time < window_end):
            continue

        if deal.deal_type is MT5DealType.NON_TRADING:
            contributions.append(Decimal("0"))
            continue

        if deal.deal_type is MT5DealType.UNKNOWN:
            blocked_reason_set.add(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE)
            unsafe_tickets.append(deal.ticket)
            continue

        contribution, reason = classify_trading_deal(deal)
        if reason is not None:
            blocked_reason_set.add(reason)
            unsafe_tickets.append(deal.ticket)
        else:
            assert contribution is not None
            contributions.append(contribution)

    if blocked_reason_set:
        reasons = tuple(reason for reason in _REASON_ORDER if reason in blocked_reason_set)
        return MT5RealizedDailyPnLAssessment(
            as_of=as_of,
            trading_day_key=trading_day_key,
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=reasons,
            unsafe_deal_tickets=tuple(unsafe_tickets),
        )

    total = sum(contributions, Decimal("0"))
    return MT5RealizedDailyPnLAssessment(
        as_of=as_of, trading_day_key=trading_day_key, outcome=MT5RealizedPnLOutcome.READY, realized_daily_pnl=total
    )


__all__ = ["MT5HistoryReadStatus", "classify_trading_deal", "compute_realized_daily_pnl"]
