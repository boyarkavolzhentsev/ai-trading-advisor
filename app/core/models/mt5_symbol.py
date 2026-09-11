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

    Deliberately excludes ``digits`` (redundant with ``point``), ``trade_
    tick_value_profit`` (every Stage 10C calculation is loss-bounding; the
    profit-side tick value is never read), ``contract_size``/currency fields
    (``trade_tick_value_loss`` already expresses monetary value in account
    currency per MT5's own documented semantics), and ``trade_freeze_level``
    (governs order modification near market - irrelevant since Stage 10C
    never sends or modifies an order).

    ``point`` (corrective review, "MT5 BROKER STOP-LEVEL SEMANTICS") IS
    included, deliberately separate from ``trade_tick_size``: real
    MetaTrader5 semantics document ``SYMBOL_TRADE_STOPS_LEVEL`` as a count of
    POINTS (``SYMBOL_POINT``), never ticks - the two are distinct, broker-
    reported symbol properties that must never be assumed identical (a
    broker MAY set them equal for a given symbol, but nothing in the MT5 API
    guarantees it). ``trade_tick_size``/``trade_tick_value_loss`` remain the
    sole basis for every monetary risk/sizing formula (Stage 10C never uses
    ``point`` for money math) - ``point`` exists in this model for exactly
    one purpose: converting ``trade_stops_level`` into a price distance for
    broker minimum-stop-distance validation, never for risk arithmetic.
    """

    as_of: Timestamp
    symbol: Symbol
    trade_tick_size: Decimal
    trade_tick_value_loss: Decimal
    point: Decimal
    volume_min: Decimal
    volume_max: Decimal
    volume_step: Decimal
    trade_stops_level: Annotated[int, Field(ge=0)]
    trade_mode: MT5SymbolTradeMode
    bid: Decimal
    ask: Decimal


__all__ = ["MT5SymbolFacts"]
