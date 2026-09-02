"""Stage 10C pure account-wide open-risk-to-stop assessment.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock - a deterministic, synchronous function of its explicit
arguments only (``as_of``, already-normalized positions, and already-
gathered symbol facts). Mirrors ``app.mt5.rollover``/``app.risk.engine`` one
architectural layer over: expected assessment states are typed return
values, never exceptions.

The impure boundary (``app.mt5.client``, and whatever future caller gathers
``symbol_facts_by_symbol`` for every distinct symbol among the open
positions) is responsible for reading positions/symbol facts and obtaining
``as_of`` - this module never gathers any of them itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from app.core.enums.mt5_position import MT5OpenRiskBlockReason, MT5OpenRiskOutcome
from app.core.enums.order import OrderSide
from app.core.models.base import Timestamp
from app.core.models.mt5_position import MT5OpenRiskAssessment, MT5Position
from app.core.models.mt5_symbol import MT5SymbolFacts

MT5PositionsReadStatus = Literal["OK", "UNAVAILABLE", "UNMAPPABLE_POSITION_SIDE"]
"""What ``MT5Client.positions()`` observed. Defined here (the pure module)
rather than in the impure ``app.mt5.client`` so this module never depends on
its own impure counterpart - ``client.py`` imports this alias instead,
mirroring ``app.mt5.rollover.PersistedStateReadStatus``'s identical
precedent. ``UNAVAILABLE`` (connectivity not ``AVAILABLE``, or the raw
``positions_get()`` call itself returned ``None``) is distinguished from
``OK`` with an empty tuple (a successful query confirming zero open
positions) - collapsing the two would fabricate "confirmed no open
positions" when the account/terminal state is genuinely unknown, exactly
the class of defect this design exists to prevent (mirrors ``account_facts()``'s
own ``None``-vs-populated distinction one layer over)."""

_REASON_ORDER: tuple[MT5OpenRiskBlockReason, ...] = tuple(MT5OpenRiskBlockReason)
"""A locally-owned copy of the canonical reason order - not imported from
``app.core.models.mt5_position`` (whose own model validator independently
re-derives the identical order to self-validate ``MT5OpenRiskAssessment``),
mirroring the Stage 5A/6A/6C/7/8/9/10B precedent of the operational
component and the result model's self-validation maintaining independent
copies of the same primitive rather than cross-importing one from the
other."""


def _is_protected(position: MT5Position) -> bool:
    """Entry/stop protected-profit classification - never consults
    ``price_current``, tick economics, or symbol facts, per the approved
    V1 rule: those facts are not mathematically necessary once contribution
    has already been safely bounded to zero."""
    if position.side is OrderSide.BUY:
        return position.stop_loss is not None and position.stop_loss >= position.price_open
    return position.stop_loss is not None and position.stop_loss <= position.price_open


def _position_contribution(
    position: MT5Position, symbol_facts_by_symbol: Mapping[str, MT5SymbolFacts]
) -> tuple[Decimal | None, MT5OpenRiskBlockReason | None]:
    """One position's contribution, or the reason it cannot be safely
    assessed. Returns ``(value, None)`` on success, ``(None, reason)`` on
    failure - never both, never neither."""
    if position.stop_loss is None:
        return None, MT5OpenRiskBlockReason.NO_PROTECTIVE_STOP

    if _is_protected(position):
        return Decimal("0"), None

    if position.price_current <= 0:
        return None, MT5OpenRiskBlockReason.INVALID_CURRENT_PRICE

    facts = symbol_facts_by_symbol.get(position.symbol)
    if facts is None:
        return None, MT5OpenRiskBlockReason.SYMBOL_UNAVAILABLE

    if facts.trade_tick_size <= 0 or facts.trade_tick_value_loss <= 0:
        return None, MT5OpenRiskBlockReason.INVALID_TICK_ECONOMICS

    if position.side is OrderSide.BUY:
        price_distance = max(Decimal("0"), position.price_current - position.stop_loss)
    else:
        price_distance = max(Decimal("0"), position.stop_loss - position.price_current)

    risk_per_volume_unit = (price_distance / facts.trade_tick_size) * facts.trade_tick_value_loss
    return risk_per_volume_unit * position.volume, None


def assess_open_risk(
    *,
    as_of: Timestamp,
    positions: tuple[MT5Position, ...],
    symbol_facts_by_symbol: Mapping[str, MT5SymbolFacts],
) -> MT5OpenRiskAssessment:
    """The account-wide aggregation: ``READY`` only if every position is
    safely assessable; if ANY position is unsafe, the whole assessment is
    ``BLOCKED`` - no partial sum, no silently-excluded ticket."""
    contributions: list[Decimal] = []
    blocked_reason_set: set[MT5OpenRiskBlockReason] = set()
    unsafe_tickets: list[int] = []

    for position in positions:
        contribution, reason = _position_contribution(position, symbol_facts_by_symbol)
        if reason is not None:
            blocked_reason_set.add(reason)
            unsafe_tickets.append(position.ticket)
        else:
            assert contribution is not None
            contributions.append(contribution)

    if blocked_reason_set:
        reasons = tuple(reason for reason in _REASON_ORDER if reason in blocked_reason_set)
        return MT5OpenRiskAssessment(
            as_of=as_of,
            outcome=MT5OpenRiskOutcome.BLOCKED,
            blocked_reasons=reasons,
            unsafe_tickets=tuple(unsafe_tickets),
        )

    total = sum(contributions, Decimal("0"))
    return MT5OpenRiskAssessment(as_of=as_of, outcome=MT5OpenRiskOutcome.READY, current_open_risk_to_stop=total)


__all__ = ["MT5PositionsReadStatus", "assess_open_risk"]
