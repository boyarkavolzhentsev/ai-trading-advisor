"""Raw MT5 rate -> internal ``OHLCVCandle`` normalization.

Pure functions only: no MT5/MetaTrader5 import, no I/O, no decisions beyond
"is this bar usable." Anything that does not fit the expected shape raises
``InvalidProviderResponseError`` rather than being repaired - mirrors
``app.market_data.providers.binance.mapper``'s own established convention
one provider over.

``volume = tick_volume`` (confirmed MT5 Price Authority design decision):
the live audit found ``real_volume`` zero/unusable for BTCUSDt, and no
Technical algorithm in this repository assumes exchange-traded volume
semantics - ``real_volume`` is therefore never read here.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.models.candle import OHLCVCandle
from app.core.models.mt5_rate import MT5RawRate
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.providers.mt5.timezone import normalize_mt5_server_timestamp


def map_mt5_rate(raw: MT5RawRate, *, server_timezone: str) -> OHLCVCandle:
    """Map one raw MT5 bar onto ``OHLCVCandle``.

    Raises:
        InvalidProviderResponseError: the raw timestamp could not be
            normalized to UTC (DST gap/ambiguity), a price is not strictly
            positive, ``tick_volume`` is negative, or the mapped OHLC values
            fail ``OHLCVCandle``'s own high/low/open/close consistency
            validator. Never repaired - a malformed bar is dropped by the
            caller, not silently fixed up.
    """
    try:
        timestamp = normalize_mt5_server_timestamp(raw.epoch_seconds, server_timezone)
    except ValueError as exc:
        raise InvalidProviderResponseError(
            f"MT5 rate at epoch {raw.epoch_seconds} could not be normalized under {server_timezone!r}: {exc}"
        ) from exc

    if raw.open <= 0 or raw.high <= 0 or raw.low <= 0 or raw.close <= 0:
        raise InvalidProviderResponseError(f"MT5 rate at epoch {raw.epoch_seconds} has a non-positive price")
    if raw.tick_volume < 0:
        raise InvalidProviderResponseError(f"MT5 rate at epoch {raw.epoch_seconds} has negative tick_volume")

    try:
        return OHLCVCandle(
            timestamp=timestamp,
            open=raw.open,
            high=raw.high,
            low=raw.low,
            close=raw.close,
            volume=Decimal(raw.tick_volume),
        )
    except ValueError as exc:  # OHLCVCandle's own high/low/open/close range validator
        raise InvalidProviderResponseError(
            f"MT5 rate at epoch {raw.epoch_seconds} failed OHLC consistency validation: {exc}"
        ) from exc


def map_mt5_rates(raws: Sequence[MT5RawRate], *, server_timezone: str) -> list[OHLCVCandle]:
    """Map a chronologically ordered sequence of raw MT5 bars, preserving
    order. Raises on the first unusable bar - no partial/best-effort list."""
    return [map_mt5_rate(raw, server_timezone=server_timezone) for raw in raws]


__all__ = ["map_mt5_rate", "map_mt5_rates"]
