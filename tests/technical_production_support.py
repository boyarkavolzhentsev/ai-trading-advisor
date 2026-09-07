"""Shared fixtures for Stage 0B Technical production composer tests.

Everything here runs against a fake, in-process Futures OHLCV provider - no
real network access happens anywhere in this module or in any test that
imports it. Mirrors ``tests/flow_realtime_bootstrap_support.py``'s own
fake-provider convention one contour over.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.timeframes import timeframe_duration
from app.technical.alignment import expected_open_time
from app.technical.production import TechnicalProductionConfig

SYMBOL = "BTCUSDT"
CONTRACT_TYPE = ContractType.PERPETUAL
NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def make_config(symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE) -> TechnicalProductionConfig:
    return TechnicalProductionConfig(symbol=symbol, contract_type=contract_type)


def make_candles(
    timeframe: Timeframe,
    count: int,
    *,
    as_of: datetime,
    start_price: Decimal = Decimal(100),
) -> list[OHLCVCandle]:
    """Build ``count`` aligned, contiguous candles ending at (and including)
    the timeframe boundary at or before ``as_of``.

    The final candle in the returned list opens exactly on
    ``expected_open_time(as_of, timeframe)`` - it is the CURRENT (possibly
    still-forming, exactly as a real provider response would look)
    candle as of ``as_of``, never one candle later. Deterministic, strictly
    increasing close prices - never a fabricated flat series - so
    calculators relying on non-zero movement have real signal to work with.
    """
    duration = timeframe_duration(timeframe)
    latest_open = expected_open_time(as_of, timeframe)
    candles = []
    for i in range(count):
        open_time = latest_open - duration * (count - 1 - i)
        close_price = start_price + i
        candles.append(
            OHLCVCandle(
                timestamp=open_time,
                open=close_price - Decimal("0.5"),
                high=close_price + Decimal("1"),
                low=close_price - Decimal("1"),
                close=close_price,
                volume=Decimal(10),
            )
        )
    return candles


class FakeFuturesOHLCVProvider:
    """Fake Futures OHLCV provider, structurally matching
    ``FuturesMarketDataProvider.get_ohlcv`` exactly, for tests only.

    Records every call for order/parameter assertions. A per-timeframe
    response is either a scripted candle list (returned, then left in place
    for subsequent calls unless replaced) or a scripted exception (raised,
    then left in place unless replaced) - never both at once.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, Timeframe, int]] = []
        self._responses: dict[Timeframe, list[OHLCVCandle] | Exception] = {}

    def set_response(self, timeframe: Timeframe, candles: list[OHLCVCandle]) -> None:
        self._responses[timeframe] = list(candles)

    def fail(self, timeframe: Timeframe, exc: Exception) -> None:
        self._responses[timeframe] = exc

    def get_ohlcv(self, symbol: str, timeframe: Timeframe, limit: int = 100) -> list[OHLCVCandle]:
        self.calls.append((symbol, timeframe, limit))
        response = self._responses.get(timeframe, [])
        if isinstance(response, Exception):
            raise response
        return list(response)


__all__ = [
    "CONTRACT_TYPE",
    "NOW",
    "SYMBOL",
    "FakeFuturesOHLCVProvider",
    "make_candles",
    "make_config",
]
