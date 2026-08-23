"""Slow REST side-channel cache for funding-interval-hours.

The mark-price WebSocket stream never discloses the funding interval; this
polls the existing REST ``fundingInfo`` capability (Stage 1B, unchanged) on
a coarse cadence and caches the result so ``mapper.map_mark_price`` can
populate ``FundingRate.funding_interval_hours`` without a REST round trip on
every tick, and without ever hard-coding a duration - a symbol not (yet)
disclosed by the cache stays ``None``, exactly as the REST provider already
behaves.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.market_data.exceptions import MarketDataError
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures import mapper as rest_mapper
from app.market_data.providers.binance.futures.constants import FUNDING_INFO_PATH

FetchAllFn = Callable[[], Awaitable[dict[str, int]]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def make_binance_fetch_all(rest_client: BinanceRestClient) -> FetchAllFn:
    """Build a ``fetch_all`` for :class:`FundingIntervalCache` from an
    already-configured Binance futures REST client.

    Runs the existing synchronous ``BinanceRestClient.get`` in a worker
    thread so it never blocks the event loop - Stage 1A/1B's REST layer is
    reused exactly as-is, not rewritten as async.
    """

    async def fetch_all() -> dict[str, int]:
        payload = await asyncio.to_thread(rest_client.get, FUNDING_INFO_PATH)
        result: dict[str, int] = {}
        if not isinstance(payload, list):
            return result
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            symbol = entry.get("symbol")
            if not isinstance(symbol, str):
                continue
            try:
                hours = rest_mapper.extract_funding_interval_hours([entry], symbol)
            except MarketDataError:
                continue
            if hours is not None:
                result[symbol] = hours
        return result

    return fetch_all


class FundingIntervalCache:
    """Refreshes a symbol -> funding-interval-hours mapping on a slow cadence."""

    def __init__(
        self,
        fetch_all: FetchAllFn,
        *,
        refresh_seconds: float = 3600.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetch_all = fetch_all
        self._refresh_seconds = refresh_seconds
        self._clock = clock or _utc_now
        self._cache: dict[str, int] = {}
        self._last_refresh: datetime | None = None

    def get(self, symbol: str) -> int | None:
        """Return the last cached interval for ``symbol``, or ``None`` if
        not (yet) disclosed - never a hard-coded default."""
        return self._cache.get(symbol.upper())

    def is_stale(self) -> bool:
        if self._last_refresh is None:
            return True
        return (self._clock() - self._last_refresh).total_seconds() >= self._refresh_seconds

    async def refresh_if_stale(self) -> None:
        """Refresh the cache if due. Failures degrade gracefully: the
        previous cache (possibly empty) is kept, never raised to the caller,
        since this is a best-effort side-channel for an optional field."""
        if not self.is_stale():
            return
        try:
            self._cache = await self._fetch_all()
        except MarketDataError:
            pass  # keep the previous cache; funding_interval_hours stays as last known (or None)
        finally:
            self._last_refresh = self._clock()


__all__ = ["FundingIntervalCache", "make_binance_fetch_all"]
