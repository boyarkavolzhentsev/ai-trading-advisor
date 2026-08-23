"""Binance implementation of ``FuturesMarketDataProvider``.

Wiring only: fetch (client) -> normalize (mapper) -> validate -> return domain
models. No strategy, indicator or ``CryptoFlowSnapshot`` aggregation happens
here - combining these reads across sources is the future Flow Supervisor's
job (``app/flow``), not this adapter's.

REST-based, USD-M perpetual contracts only. Liquidations, a maintained order
book, real-time taker flow and a live mark-price/funding stream are all
deferred to the WebSocket transport added in a later stage; see
``app.market_data.providers.binance.futures.liquidations`` for the current
liquidation stub.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

from app.core.enums.market import Timeframe
from app.core.models.data_quality import DataQuality
from app.core.models.funding import FundingRate
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookSnapshot
from app.core.models.taker_flow import TakerFlowSnapshot
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.protocols import DEFAULT_OHLCV_LIMIT
from app.market_data.provenance import MarketDataProvenance, MarketDataSource
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures import mapper
from app.market_data.providers.binance.futures.constants import (
    BINANCE_FUTURES_BASE_URL,
    DEFAULT_DEPTH_LIMIT,
    DEFAULT_TIMEOUT_SECONDS,
    DEPTH_LIMITS,
    DEPTH_PATH,
    FUNDING_INFO_PATH,
    KLINES_PATH,
    MAX_KLINES_LIMIT,
    OPEN_INTEREST_PATH,
    PREMIUM_INDEX_PATH,
    PROVIDER_NAME,
)
from app.market_data.validators import DataQualityValidator


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BinanceFuturesMarketDataProvider:
    """Public Binance USD-M perpetual futures data as internal domain contracts."""

    def __init__(
        self,
        client: BinanceRestClient | None = None,
        *,
        validator: DataQualityValidator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the adapter.

        Args:
            client: low-level REST client; a default one pointed at the
                futures base URL is created if omitted.
            validator: data quality validator; a default one is used if omitted.
            clock: UTC "now" source, injectable to keep tests deterministic.
        """
        self._client = client if client is not None else BinanceRestClient(
            base_url=BINANCE_FUTURES_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS
        )
        self._validator = validator if validator is not None else DataQualityValidator()
        self._clock = clock if clock is not None else _utc_now

    def get_funding_rate(self, symbol: str) -> FundingRate:
        """Return the current funding state of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        payload = self._client.get(PREMIUM_INDEX_PATH, {"symbol": requested})
        fetched_at = self._clock()
        provenance = self._provenance(MarketDataSource.FUNDING_RATE, requested, fetched_at)

        funding_info_payload = self._client.get(FUNDING_INFO_PATH)
        funding_interval_hours = mapper.extract_funding_interval_hours(
            funding_info_payload, requested
        )

        funding_rate = mapper.map_funding_rate(
            payload,
            funding_interval_hours=funding_interval_hours,
            source=provenance.label,
            fetched_at=fetched_at,
        )
        self._require_valid(
            self._validator.validate_symbol(
                expected=requested, received=funding_rate.symbol, provenance=provenance, now=fetched_at
            ),
            provenance,
        )
        return funding_rate

    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Return the current total open interest of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        payload = self._client.get(OPEN_INTEREST_PATH, {"symbol": requested})
        fetched_at = self._clock()
        provenance = self._provenance(MarketDataSource.OPEN_INTEREST, requested, fetched_at)

        open_interest = mapper.map_open_interest(payload, source=provenance.label, fetched_at=fetched_at)
        self._require_valid(
            self._validator.validate_symbol(
                expected=requested, received=open_interest.symbol, provenance=provenance, now=fetched_at
            ),
            provenance,
        )
        return open_interest

    def get_taker_flow(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
    ) -> list[TakerFlowSnapshot]:
        """Return up to ``limit`` taker buy/sell volume snapshots, oldest first."""
        requested = mapper.normalize_symbol(symbol)
        interval = mapper.to_futures_interval(timeframe)
        if not 1 <= limit <= MAX_KLINES_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_KLINES_LIMIT}, got {limit}")

        payload = self._client.get(
            KLINES_PATH, {"symbol": requested, "interval": interval, "limit": limit}
        )
        fetched_at = self._clock()
        provenance = self._provenance(
            MarketDataSource.TAKER_FLOW, requested, fetched_at, timeframe=timeframe
        )
        if not payload:
            raise InvalidProviderResponseError(
                f"{provenance.label} data for {requested} rejected: empty taker flow result"
            )
        return mapper.map_taker_flow(
            payload, symbol=requested, timeframe=timeframe, source=provenance.label
        )

    def get_order_book_snapshot(
        self,
        symbol: str,
        limit: int = DEFAULT_DEPTH_LIMIT,
    ) -> OrderBookSnapshot:
        """Return a bounded, point-in-time order book snapshot of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        if limit not in DEPTH_LIMITS:
            allowed = ", ".join(str(value) for value in sorted(DEPTH_LIMITS))
            raise ValueError(f"limit must be one of {allowed}, got {limit}")

        payload = self._client.get(DEPTH_PATH, {"symbol": requested, "limit": limit})
        fetched_at = self._clock()
        provenance = self._provenance(MarketDataSource.ORDER_BOOK, requested, fetched_at)
        return mapper.map_order_book_snapshot(
            payload, symbol=requested, source=provenance.label, fetched_at=fetched_at
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @staticmethod
    def _provenance(
        source: MarketDataSource,
        symbol: str,
        fetched_at: datetime,
        *,
        timeframe: Timeframe | None = None,
    ) -> MarketDataProvenance:
        return MarketDataProvenance(
            provider=PROVIDER_NAME,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            fetched_at=fetched_at,
        )

    @staticmethod
    def _require_valid(quality: DataQuality, provenance: MarketDataProvenance) -> None:
        """Abort the call when the validator rejects the data."""
        if quality.is_valid:
            return
        details = "; ".join(quality.warnings) or "unspecified quality failure"
        raise InvalidProviderResponseError(
            f"{provenance.label} data for {provenance.symbol} rejected: {details}"
        )


__all__ = ["BinanceFuturesMarketDataProvider"]
