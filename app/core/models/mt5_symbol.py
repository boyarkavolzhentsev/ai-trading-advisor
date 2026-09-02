"""Stage 10C normalized symbol/broker trading-constraint output contract.

``MT5SymbolFacts`` is a raw-but-normalized combination of one
``symbol_info()`` and one ``symbol_info_tick()`` call - the narrowest set of
broker facts that safely support open-risk pricing, broker volume
normalization, and post-normalization risk verification, using tick-based
economics that stay valid across FX, metals, indices/CFDs and crypto CFDs
alike (never a pip/point/contract-size formula that would only hold for one
asset class).

Every price/tick/volume field here is deliberately permissive (plain
``Decimal``, no ``gt=0``/``ge=0`` constraint): an invalid broker-reported
value (``trade_tick_size <= 0``, ``volume_step <= 0``, ...) is a legitimate,
if rare, broker/runtime condition to be interpreted as a typed business
outcome by ``app.mt5.risk``/``app.mt5.sizing`` - never a construction-time
rejection, mirroring ``MT5AccountFacts``'s own permissive-then-interpreted
treatment of live broker facts.
"""

from __future__ import annotations

from typing import Annotated
from decimal import Decimal

from pydantic import Field

from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.models.base import DomainModel, Symbol, Timestamp


class MT5SymbolFacts(DomainModel):
    """Normalized, one-call-pair snapshot of one symbol's trading
    constraints and current quote.

    Deliberately excludes ``point``/``digits`` (the approved formulas use
    ``trade_tick_size`` directly, never pip/point math), ``trade_tick_value_
    profit`` (every Stage 10C calculation is loss-bounding; the profit-side
    tick value is never read), ``contract_size``/currency fields
    (``trade_tick_value_loss`` already expresses monetary value in account
    currency per MT5's own documented semantics), and ``trade_freeze_level``
    (governs order modification near market - irrelevant since Stage 10C
    never sends or modifies an order).
    """

    as_of: Timestamp
    symbol: Symbol
    trade_tick_size: Decimal
    trade_tick_value_loss: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    trade_stops_level: Annotated[int, Field(ge=0)]
    trade_mode: MT5SymbolTradeMode
    bid: Decimal
    ask: Decimal


__all__ = ["MT5SymbolFacts"]
