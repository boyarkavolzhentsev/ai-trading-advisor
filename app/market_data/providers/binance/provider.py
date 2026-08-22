"""Binance implementation of ``MarketDataProvider``.

Wiring only: fetch (client) -> normalize (mapper) -> validate (validator) ->
return domain models. No strategy, indicator or sizing logic lives here.

Quality policy of this adapter:

- an invalid verdict aborts the call with ``InvalidProviderResponseError``;
- a stale-but-structurally-valid series is returned and logged as a warning, so
  future components can decide how to degrade.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.data_quality import DataQuality
from app.core.models.instrument import InstrumentMetadata
from app.core.models.quote import BidAskQuote, PriceQuote
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.protocols import DEFAULT_OHLCV_LIMIT
from app.market_data.providers.binance import mapper
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.constants import (
    BOOK_TICKER_PATH,
    EXCHANGE_INFO_PATH,
    KLINES_PATH,
    MAX_KLINES_LIMIT,
    PROVIDER_NAME,
    TICKER_PRICE_PATH,
)
from app.market_data.provenance import MarketDataProvenance, MarketDataSource
from app.market_data.validators import DataQualityValidator

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BinanceMarketDataProvider:
    """Public Binance Spot market data as internal domain contracts."""

    def __init__(
        self,
        client: BinanceRestClient | None = None,
        *,
        validator: DataQualityValidator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Create the adapter.

        Args:
            client: low-level REST client; a default one is created if omitted.
            validator: data quality validator; a default one is used if omitted.
            clock: UTC "now" source, injectable to keep tests deterministic.
        """
        self._client = client if client is not None else BinanceRestClient()
        self._validator = validator if validator is not None else DataQualityValidator()
        self._clock = clock if clock is not None else _utc_now

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Return the last traded price of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        payload = self._client.get(TICKER_PRICE_PATH, {"symbol": requested})
        fetched_at = self._clock()
        provenance = self._provenance(MarketDataSource.TICKER_PRICE, requested, fetched_at)

        quote = mapper.map_price_quote(payload, source=provenance.label, fetched_at=fetched_at)
        self._require_valid(
            self._validator.validate_symbol(
                expected=requested, received=quote.symbol, provenance=provenance, now=fetched_at
            ),
            provenance,
        )
        return quote

    def get_bid_ask(self, symbol: str) -> BidAskQuote:
        """Return the best bid and ask of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        payload = self._client.get(BOOK_TICKER_PATH, {"symbol": requested})
        fetched_at = self._clock()
        provenance = self._provenance(MarketDataSource.BOOK_TICKER, requested, fetched_at)

        ticker = mapper.normalize_book_ticker(payload)
        self._require_valid(
            self._validator.validate_symbol(
                expected=requested, received=ticker.symbol, provenance=provenance, now=fetched_at
            ),
            provenance,
        )
        self._require_valid(
            self._validator.validate_bid_ask(
                ticker.bid, ticker.ask, provenance=provenance, now=fetched_at
            ),
            provenance,
        )
        return mapper.to_bid_ask_quote(ticker, source=provenance.label, fetched_at=fetched_at)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
    ) -> list[OHLCVCandle]:
        """Return up to ``limit`` closed-or-forming candles, oldest first."""
        requested = mapper.normalize_symbol(symbol)
        interval = mapper.to_binance_interval(timeframe)
        if not 1 <= limit <= MAX_KLINES_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_KLINES_LIMIT}, got {limit}")

        payload = self._client.get(
            KLINES_PATH, {"symbol": requested, "interval": interval, "limit": limit}
        )
        fetched_at = self._clock()
        provenance = self._provenance(
            MarketDataSource.KLINES, requested, fetched_at, timeframe=timeframe
        )

        candles = mapper.map_klines(payload)
        quality = self._validator.validate_candles(
            candles, provenance=provenance, timeframe=timeframe, now=fetched_at
        )
        self._require_valid(quality, provenance)
        if quality.is_stale:
            logger.warning(
                "stale OHLCV from %s for %s %s: %s",
                provenance.label,
                requested,
                timeframe.value,
                "; ".join(quality.warnings),
            )
        return candles

    def get_instrument_metadata(self, symbol: str) -> InstrumentMetadata:
        """Return the Binance specification of ``symbol``."""
        requested = mapper.normalize_symbol(symbol)
        payload = self._client.get(EXCHANGE_INFO_PATH, {"symbol": requested})
        fetched_at = self._clock()
        provenance = self._provenance(
            MarketDataSource.EXCHANGE_INFO,
            requested,
            fetched_at,
            provider_timestamp=self._server_time(payload),
        )
        return mapper.map_instrument_metadata(
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
    def _server_time(payload: Any) -> datetime | None:
        """Exchange-info server time, ignored when the payload is unusable."""
        try:
            return mapper.extract_server_time(payload)
        except InvalidProviderResponseError:
            return None

    @staticmethod
    def _provenance(
        source: MarketDataSource,
        symbol: str,
        fetched_at: datetime,
        *,
        timeframe: Timeframe | None = None,
        provider_timestamp: datetime | None = None,
    ) -> MarketDataProvenance:
        return MarketDataProvenance(
            provider=PROVIDER_NAME,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            fetched_at=fetched_at,
            provider_timestamp=provider_timestamp,
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


__all__ = ["BinanceMarketDataProvider"]
