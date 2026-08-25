"""Stage 3A orchestration: strict per-(symbol, contract_type, timeframe)
state isolation.

``TechnicalFeatureEngine`` owns bounded candle history and composes a
``TechnicalFeatureSnapshot`` from it via the pure calculators in this
package. It performs no network I/O, no polling and no interpretation -
only state isolation and wiring. No symbol/timeframe is ever hard-coded:
every method is parameterized by ``(symbol, contract_type, timeframe)``,
and each triple gets its own independent ``SymbolTimeframeHistory``.

Ingestion is strict: a candle whose timestamp does not sit on its
timeframe's UTC epoch boundary is rejected (``MisalignedCandleError``), and
a candle whose timestamp duplicates one already retained for the same key
is rejected (``DuplicateCandleTimestampError``) - both fail loudly rather
than silently degrading quality, mirroring
``app.flow_supervisor.errors``'s "signals a mistake, never a legitimate
market condition" stance. A rejected duplicate leaves existing history
completely untouched.

Candle retention is chronologically deterministic BY TIMESTAMP, not by
insertion order: out-of-order insertion is fully supported, and after
ingestion the retained bounded history always holds the chronologically
newest ``capacity`` candles regardless of the order they arrived in (see
``app.technical.candle_store.ChronologicalCandleStore``). A late-arriving
old candle can therefore never evict a chronologically newer one, and a
late-arriving new candle always evicts the chronologically oldest retained
candle. ``history.candles.latest()`` already returns candles sorted
ascending by timestamp, so ``build_snapshot`` consumes it directly with no
separate re-sort step.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.feature_status import FeatureStatus
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical.alignment import is_aligned, split_closed_and_forming
from app.technical.candle_structure import compute_candle_structure_features
from app.technical.errors import MisalignedCandleError
from app.technical.history import SymbolTimeframeHistory
from app.technical.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS, compute_market_structure_features
from app.technical.momentum import DEFAULT_ROC_PERIOD, DEFAULT_RSI_PERIOD, compute_momentum_features
from app.technical.moving_average import DEFAULT_MA_PERIODS, compute_moving_average_features
from app.technical.quality import worse_of_many
from app.technical.range_state import DEFAULT_RANGE_STATE_LOOKBACK, compute_range_state_features
from app.technical.trend import DEFAULT_TREND_LOOKBACK, compute_trend_features
from app.technical.volatility import DEFAULT_ATR_PERIOD, DEFAULT_VOLATILITY_LOOKBACK, compute_volatility_features


class TechnicalFeatureEngine:
    """Owns bounded per-(symbol, contract_type, timeframe) history and builds snapshots."""

    def __init__(
        self,
        *,
        trend_lookback: int = DEFAULT_TREND_LOOKBACK,
        left_bars: int = DEFAULT_LEFT_BARS,
        right_bars: int = DEFAULT_RIGHT_BARS,
        atr_period: int = DEFAULT_ATR_PERIOD,
        volatility_lookback: int = DEFAULT_VOLATILITY_LOOKBACK,
        roc_period: int = DEFAULT_ROC_PERIOD,
        rsi_period: int = DEFAULT_RSI_PERIOD,
        ma_periods: Sequence[int] = DEFAULT_MA_PERIODS,
        range_state_lookback: int = DEFAULT_RANGE_STATE_LOOKBACK,
    ) -> None:
        self._trend_lookback = trend_lookback
        self._left_bars = left_bars
        self._right_bars = right_bars
        self._atr_period = atr_period
        self._volatility_lookback = volatility_lookback
        self._roc_period = roc_period
        self._rsi_period = rsi_period
        self._ma_periods = tuple(ma_periods)
        self._range_state_lookback = range_state_lookback
        self._state: dict[tuple[str, ContractType, Timeframe], SymbolTimeframeHistory] = {}

    def _history_for(self, symbol: str, contract_type: ContractType, timeframe: Timeframe) -> SymbolTimeframeHistory:
        key = (symbol.upper(), contract_type, timeframe)
        history = self._state.get(key)
        if history is None:
            history = SymbolTimeframeHistory.with_capacity()
            self._state[key] = history
        return history

    def history_for(self, symbol: str, contract_type: ContractType, timeframe: Timeframe) -> SymbolTimeframeHistory:
        """Expose the bounded history of one symbol/contract type/timeframe (read/inspect only)."""
        return self._history_for(symbol, contract_type, timeframe)

    def record_candle(
        self, symbol: str, contract_type: ContractType, timeframe: Timeframe, candle: OHLCVCandle
    ) -> None:
        """Ingest one candle, failing loudly on misalignment or a duplicate timestamp.

        Duplicate-timestamp rejection is atomic (see
        ``ChronologicalCandleStore.append``): a rejected candle leaves
        existing retained history completely untouched. Out-of-order
        arrival is fully supported - retention is reconciled by timestamp,
        not insertion order.
        """
        symbol = symbol.upper()
        if not is_aligned(candle.timestamp, timeframe):
            raise MisalignedCandleError(
                f"candle timestamp {candle.timestamp.isoformat()} is not aligned to {timeframe} boundaries"
            )
        history = self._history_for(symbol, contract_type, timeframe)
        history.candles.append(candle)

    def record_candles(
        self,
        symbol: str,
        contract_type: ContractType,
        timeframe: Timeframe,
        candles: Sequence[OHLCVCandle],
    ) -> None:
        """Ingest multiple candles in the supplied order via :meth:`record_candle`."""
        for candle in candles:
            self.record_candle(symbol, contract_type, timeframe, candle)

    def build_snapshot(
        self,
        *,
        symbol: str,
        contract_type: ContractType,
        timeframe: Timeframe,
        as_of: datetime,
        source: str = "technical_engine",
    ) -> TechnicalFeatureSnapshot:
        """Compose one synchronized ``TechnicalFeatureSnapshot`` from retained history.

        ``as_of`` must be supplied explicitly by the caller - never read
        from the wall clock here - so the result is fully reproducible.
        Only CLOSED candles (as of ``as_of``) ever enter a rolling
        calculation; the most recent still-forming candle, if any, is
        exposed separately as ``live_candle``.
        """
        symbol = symbol.upper()
        history = self._history_for(symbol, contract_type, timeframe)
        candles = history.candles.latest()  # already sorted ascending by timestamp
        closed, live_candle = split_closed_and_forming(candles, timeframe, as_of)

        trend = compute_trend_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, lookback=self._trend_lookback, source=source,
        )
        market_structure = compute_market_structure_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, left_bars=self._left_bars, right_bars=self._right_bars, source=source,
        )
        volatility = compute_volatility_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, atr_period=self._atr_period, volatility_lookback=self._volatility_lookback,
            source=source,
        )
        momentum = compute_momentum_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, roc_period=self._roc_period, rsi_period=self._rsi_period, source=source,
        )
        moving_average = compute_moving_average_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, periods=self._ma_periods, source=source,
        )
        candle_structure = compute_candle_structure_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe, candles=closed, source=source,
        )
        range_state = compute_range_state_features(
            symbol=symbol, contract_type=contract_type, timeframe=timeframe,
            candles=closed, lookback=self._range_state_lookback, atr_period=self._atr_period, source=source,
        )

        overall_quality = worse_of_many(
            block.status.quality
            for block in (trend, market_structure, volatility, momentum, moving_average, candle_structure, range_state)
        )
        overall_sample_count = sum(
            block.status.sample_count
            for block in (trend, market_structure, volatility, momentum, moving_average, candle_structure, range_state)
        )

        snapshot = TechnicalFeatureSnapshot(
            symbol=symbol,
            contract_type=contract_type,
            timeframe=timeframe,
            observation_time=as_of,
            last_closed_candle_time=closed[-1].timestamp if closed else None,
            live_candle=live_candle,
            trend=trend,
            market_structure=market_structure,
            volatility=volatility,
            momentum=momentum,
            moving_average=moving_average,
            candle_structure=candle_structure,
            range_state=range_state,
            status=FeatureStatus(quality=overall_quality, sample_count=overall_sample_count),
            source=source,
        )
        history.snapshots.append(snapshot)
        return snapshot


__all__ = ["TechnicalFeatureEngine"]
