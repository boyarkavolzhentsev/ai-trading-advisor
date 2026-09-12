"""Stage 10A raw MT5 OHLCV bar - read-only, pre-normalization carrier.

``epoch_seconds`` is MT5's own raw ``time`` field verbatim: broker-server
wall-clock digits encoded as epoch seconds, NOT a genuine UTC epoch instant
(see the approved MT5 Price Authority timezone design) - deliberately typed
as a plain ``int``, never ``Timestamp``, so no caller can mistake it for an
already-normalized aware datetime. Converting it to real UTC is explicitly
not this model's job; that is ``app.market_data.providers.mt5.timezone``'s
sole responsibility, one layer above ``app.mt5.client``.

Deliberately permissive (no ``gt=0`` price/volume constraint), mirroring
``MT5SymbolFacts``'s own stated philosophy: an invalid broker-reported value
is a legitimate, if rare, condition to be interpreted downstream (the MT5
OHLCV mapper) as a typed business outcome - never a construction-time
rejection here.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.models.base import DomainModel


class MT5RawRate(DomainModel):
    """One raw bar as returned by ``MT5Client.rates()`` - not yet an
    ``OHLCVCandle`` (no UTC timestamp, no OHLC-consistency/positivity
    validation). ``real_volume`` is carried through for completeness/audit
    only - the live audit found it zero/unusable for BTCUSDt, and no MT5
    OHLCV mapper ever reads it."""

    epoch_seconds: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
    real_volume: int


__all__ = ["MT5RawRate"]
