"""Stage 10C pure broker-aware final candidate sizing.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock - a deterministic, synchronous function of its explicit
arguments only. Structurally separate from ``app.mt5.risk``: an existing
open position's risk is priced from ``price_current`` toward its stop, net
of what ``floating_pnl`` already covers from ``price_open``; a not-yet-open
candidate has no entry fill yet, so its risk is priced in one step, straight
from its reference/entry price toward its stop - no protected-profit concept
applies, and no candidate-vs-existing-position netting is ever performed
(every candidate is priced as an independent new add, deliberately
conservative for NETTING accounts - see the approved Stage 10C design).

Converts one already-approved ``session_allocated_risk`` into an actionable,
broker-normalized volume - never Stage 7's stale ``recommended_units``.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.enums.trade import TradeDirection
from app.core.models.base import Timestamp
from app.core.models.mt5_sizing import MT5BrokerSizingRequest, MT5BrokerSizingResult
from app.core.models.mt5_symbol import MT5SymbolFacts

_LONG_BLOCKING_MODES: frozenset[MT5SymbolTradeMode] = frozenset(
    {MT5SymbolTradeMode.DISABLED, MT5SymbolTradeMode.SHORT_ONLY, MT5SymbolTradeMode.CLOSE_ONLY, MT5SymbolTradeMode.UNKNOWN}
)
_SHORT_BLOCKING_MODES: frozenset[MT5SymbolTradeMode] = frozenset(
    {MT5SymbolTradeMode.DISABLED, MT5SymbolTradeMode.LONG_ONLY, MT5SymbolTradeMode.CLOSE_ONLY, MT5SymbolTradeMode.UNKNOWN}
)
"""``UNKNOWN`` blocks both directions - an unrecognized trade-mode value can
never be safely claimed tradable (see ``MT5SymbolTradeMode``'s own
docstring)."""


def floor_volume_to_step(volume: Decimal, volume_min: Decimal, volume_max: Decimal, volume_step: Decimal) -> Decimal | None:
    """The approved volume_min-anchored broker grid floor - never a
    zero-anchored floor, which would misalign with a broker's actual valid
    volume grid whenever ``volume_min`` is not itself a multiple of
    ``volume_step``. Caps DOWN to ``volume_max`` before flooring (order is
    essential: flooring an uncapped raw volume first could land above
    ``volume_max``), so the greatest valid grid point never exceeds either
    ``volume_max`` or the original ``volume``, regardless of whether
    ``volume_max`` itself sits exactly on the grid. Returns ``None`` for
    invalid constraints or a result that would floor below ``volume_min``.
    """
    if volume_min <= 0 or volume_step <= 0 or volume_max < volume_min:
        return None
    capped = min(volume, volume_max)
    if capped < volume_min:
        return None
    step_count = ((capped - volume_min) / volume_step).to_integral_value(rounding=ROUND_FLOOR)
    return volume_min + step_count * volume_step


def _direction_blocked(direction: TradeDirection, trade_mode: MT5SymbolTradeMode) -> bool:
    blocking_modes = _LONG_BLOCKING_MODES if direction is TradeDirection.LONG else _SHORT_BLOCKING_MODES
    return trade_mode in blocking_modes


def compute_broker_sizing(
    *,
    as_of: Timestamp,
    request: MT5BrokerSizingRequest,
    symbol_facts: MT5SymbolFacts,
) -> MT5BrokerSizingResult:
    """The full broker-aware sizing pipeline for one candidate: resolve the
    reference price, validate tradability/tick-economics/volume-constraints/
    stop-distance, compute and grid-normalize the volume, then re-verify the
    resulting monetary risk never exceeds ``session_allocated_risk`` - exact
    Decimal throughout, never a tolerance/epsilon comparison."""
    reference_price = request.entry_price
    if reference_price is None:
        reference_price = symbol_facts.ask if request.direction is TradeDirection.LONG else symbol_facts.bid
        if reference_price <= 0:
            return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.INVALID_CURRENT_PRICE)

    if _direction_blocked(request.direction, symbol_facts.trade_mode):
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.SYMBOL_NOT_TRADABLE)

    if symbol_facts.trade_tick_size <= 0 or symbol_facts.trade_tick_value_loss <= 0:
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.INVALID_TICK_ECONOMICS)

    if symbol_facts.volume_min <= 0 or symbol_facts.volume_step <= 0 or symbol_facts.volume_max < symbol_facts.volume_min:
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.INVALID_VOLUME_CONSTRAINTS)

    valid_stop_side = (
        request.stop_loss < reference_price if request.direction is TradeDirection.LONG else request.stop_loss > reference_price
    )
    if not valid_stop_side:
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.INVALID_STOP_DISTANCE)

    price_distance = abs(reference_price - request.stop_loss)
    risk_per_volume_unit = (price_distance / symbol_facts.trade_tick_size) * symbol_facts.trade_tick_value_loss
    raw_volume = request.session_allocated_risk / risk_per_volume_unit

    normalized_volume = floor_volume_to_step(raw_volume, symbol_facts.volume_min, symbol_facts.volume_max, symbol_facts.volume_step)
    if normalized_volume is None:
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.BELOW_BROKER_MINIMUM_VOLUME)

    actual_monetary_risk = risk_per_volume_unit * normalized_volume
    if actual_monetary_risk > request.session_allocated_risk:
        return MT5BrokerSizingResult(as_of=as_of, outcome=MT5SizingOutcome.RISK_VERIFICATION_FAILED)

    return MT5BrokerSizingResult(
        as_of=as_of,
        outcome=MT5SizingOutcome.ACTIONABLE,
        broker_volume=normalized_volume,
        actual_monetary_risk=actual_monetary_risk,
    )


__all__ = ["compute_broker_sizing", "floor_volume_to_step"]
