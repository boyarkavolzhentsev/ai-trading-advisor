"""Deterministic Statistics Aggregator (Stage 9).

Aggregates an explicit ``tuple[PositionRecord, ...]`` - assembled upstream by
the future Stage 10 tracker/storage layer, never fetched here - into one
``PerformanceSnapshot``. Never touches MT5, a database, the filesystem, the
network, or the wall clock; never polls a price or decides an outcome itself
- it only counts and averages facts a caller has already normalized onto
``PositionRecord.status``/``.pnl``.

Reporting only: this module has no import path into, and is never consulted
by, ``app.statistics.session`` - Stage 9 V1 has no approved rule tying
historical performance to family eligibility, ranking, confidence, scoring,
voting, or risk allocation of any kind (see the approved Stage 9 design).

``PerformanceSnapshot`` names six count buckets: ``total_trades``, ``wins``,
``losses``, ``breakeven``, ``not_filled``, ``expired``. Exactly five
``TradeStatus`` members map onto those five named outcome buckets one-to-one
(``WIN``/``LOSS``/``BREAKEVEN``/``NOT_FILLED``/``EXPIRED``) - a signal has
settled into exactly one of these terminal states. ``total_trades`` is the
sum of those five buckets. Records whose ``status`` is ``PENDING``,
``FILLED``, ``OPEN``, ``CLOSED`` or ``CANCELLED`` describe a signal that has
not (yet) settled into one of ``PerformanceSnapshot``'s five terminal
buckets; counting them into ``total_trades`` would silently invent a bucket
the contract does not define (and Stage 9 V1 is not approved to add one), so
this aggregator excludes them entirely rather than mis-attributing them.

``max_drawdown`` is deliberately never computed in V1 and is always ``None``:
a meaningful drawdown requires both a starting-equity baseline (this
aggregator's one explicit input is the record tuple alone - no account
snapshot is supplied, by the approved design) and a well-defined, tie-safe
chronological ordering key across records (``exit_time`` is unset for
``NOT_FILLED``/``EXPIRED`` records, and falling back to input-tuple order
would make the result depend on caller-supplied ordering, breaking
determinism). Both would require inventing semantics the existing contract
does not support - reported as a design blocker rather than fabricated.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.trade import TradeStatus
from app.core.models.performance import PerformanceSnapshot
from app.core.models.position import PositionRecord

_COUNTED_STATUSES: frozenset[TradeStatus] = frozenset(
    {
        TradeStatus.WIN,
        TradeStatus.LOSS,
        TradeStatus.BREAKEVEN,
        TradeStatus.NOT_FILLED,
        TradeStatus.EXPIRED,
    }
)


class StatisticsAggregator:
    """Deterministic Stage 9 aggregator over an explicit ``PositionRecord`` history."""

    def aggregate(self, *, records: tuple[PositionRecord, ...]) -> PerformanceSnapshot:
        counted = tuple(record for record in records if record.status in _COUNTED_STATUSES)

        wins = sum(1 for record in counted if record.status is TradeStatus.WIN)
        losses = sum(1 for record in counted if record.status is TradeStatus.LOSS)
        breakeven = sum(1 for record in counted if record.status is TradeStatus.BREAKEVEN)
        not_filled = sum(1 for record in counted if record.status is TradeStatus.NOT_FILLED)
        expired = sum(1 for record in counted if record.status is TradeStatus.EXPIRED)
        total_trades = wins + losses + breakeven + not_filled + expired

        win_rate = (wins / total_trades) if total_trades > 0 else None

        pnl_values = tuple(record.pnl for record in counted if record.pnl is not None)
        expectancy = (sum(pnl_values, Decimal("0")) / len(pnl_values)) if pnl_values else None

        gross_profit = sum((pnl for pnl in pnl_values if pnl > 0), Decimal("0"))
        gross_loss = sum((-pnl for pnl in pnl_values if pnl < 0), Decimal("0"))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else None

        return PerformanceSnapshot(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            not_filled=not_filled,
            expired=expired,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            max_drawdown=None,
        )


__all__ = ["StatisticsAggregator"]
