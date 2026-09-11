"""Stage 0B Technical production wiring: real Binance Futures OHLCV -> the
existing, unmodified ``TechnicalFeatureEngine`` -> the existing, unmodified
seven Stage 3B analysts -> the existing, unmodified ``TechnicalSupervisor``.

``TechnicalProductionComposer`` owns exactly one configured ``(symbol,
contract_type)`` pair's long-lived ``TechnicalFeatureEngine`` and, on every
call to ``build_technical_result``, refreshes all six default timeframes
from a fresh REST fetch before composing the current production
``TechnicalSupervisorResult``. It owns no trading/decision logic of any
kind - no Market Evaluation, Strategy Router, Judge, Policy, Risk,
Diversification, Statistics/Session, MT5, LLM, or bot/HTTP delivery
dependency exists here (enforced by
``tests/test_technical_production_module_hygiene.py``), and it never
combines this result with Flow evidence of any kind.

Synchronous and REST-only by design: every timeframe fetch is a plain,
sequential call to an injected ``FuturesMarketDataProvider`` - no
WebSocket, no background task, no ``asyncio`` anywhere in this module. A
REST failure for one timeframe never removes that timeframe's six analyst
cells from the eventual 42-cell matrix: this composer always builds all six
``TechnicalFeatureSnapshot``s and always runs all seven analysts against
each one, feeding whatever history is currently retained (including empty
history) through unchanged. Data insufficiency therefore surfaces only
through ``FeatureStatus``/``FeatureQuality`` and analyst abstention -
``TechnicalSupervisorResult.missing_cells`` stays empty under ordinary
provider degradation - never through an omitted composition cell.

Only ``app.market_data.exceptions.MarketDataError`` is treated as ordinary,
expected provider degradation; every other exception (a Stage 3A ingestion
error, a Stage 3C supervisor invariant error, or any programming defect
from a provider/analyst) is left to propagate uncaught, mirroring Stage
0A's own established convention for distinguishing legitimate market
conditions from genuine bugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.market_data.exceptions import MarketDataError
from app.market_data.protocols import FuturesMarketDataProvider
from app.technical.alignment import split_closed_and_forming
from app.technical.engine import TechnicalFeatureEngine
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES
from app.technical_analysts.candle_structure import CandleStructureAnalyst
from app.technical_analysts.market_structure import MarketStructureAnalyst
from app.technical_analysts.momentum import MomentumAnalyst
from app.technical_analysts.moving_average import MovingAverageAnalyst
from app.technical_analysts.protocols import TechnicalAnalyst
from app.technical_analysts.range_state import RangeStateAnalyst
from app.technical_analysts.trend import TrendAnalyst
from app.technical_analysts.volatility import VolatilityAnalyst
from app.technical_supervisor.supervisor import TechnicalSupervisor

TECHNICAL_OHLCV_FETCH_LIMIT = 51
"""50 closed candles for the binding SMA(50)/EMA(50) moving-average
calculator (``app.technical.moving_average.DEFAULT_MA_PERIODS``), plus a
+1 margin for a possible still-forming final candle the provider may
return. Not owner-configurable in V1 - every other Technical tuning
parameter already has a reviewed default inside the existing, unmodified
components this module wires together."""

_ANALYSTS: tuple[TechnicalAnalyst, ...] = (
    TrendAnalyst(),
    MarketStructureAnalyst(),
    VolatilityAnalyst(),
    MomentumAnalyst(),
    MovingAverageAnalyst(),
    CandleStructureAnalyst(),
    RangeStateAnalyst(),
)
"""All seven Stage 3B specialists, zero-argument/stateless, in
``TechnicalSupervisor.DEFAULT_EXPECTED_ANALYSTS`` canonical order. Every one
of the seven is always invoked for every timeframe - abstention is a
legitimate, typed per-analyst result (``TechnicalAnalystOutcome.ABSTAINED``),
never represented by omitting a call, and the composer never inspects a
snapshot's feature-block quality to decide whether to call an analyst."""


class TechnicalProductionConfig(DomainModel):
    """The minimal V1 deployment configuration for one Technical production
    composer instance: which one ``(symbol, contract_type)`` pair it owns.
    Every other Technical tuning parameter (calculator lookbacks/periods,
    engine candle/snapshot capacities) already has a reviewed default inside
    the existing, unmodified components this module wires together and is
    deliberately not re-exposed here.
    """

    symbol: Symbol
    contract_type: ContractType


@dataclass(frozen=True, slots=True)
class TechnicalFetchFailure:
    """One timeframe's OHLCV fetch failure this cycle - a narrow operational
    fact, never a trading signal. Carries only what a caller needs to know
    something failed and what kind of failure it was: never an exception
    message, exception args, a traceback, a provider payload, a URL or
    headers."""

    timeframe: Timeframe
    error_type: str


@dataclass(frozen=True, slots=True)
class TechnicalProductionResult:
    """Narrow Stage 0B production result: the full 42-cell
    ``TechnicalSupervisorResult`` plus the one M15 market-structure fact
    Setup Construction needs, reused verbatim from the same M15 snapshot -
    never recomputed and never ``Optional`` (Stage 0B always builds all six
    snapshots, and ``compute_market_structure_features`` always returns a
    populated object, carrying ``UNAVAILABLE`` quality on empty history
    rather than being omitted). Carries no raw per-timeframe snapshot and no
    trading decision field of any kind.

    ``m15_last_closed_close`` (corrective design closure, "PROVIDER SYMBOL
    SPLIT + PRICE-BASIS RECONCILIATION") is the Binance M15 reference price
    Setup Construction needs to translate a Binance structural stop onto
    MT5's own price axis - the retained M15 candle store's own most recent
    CLOSED candle close, never the forming candle, never an extra REST call.
    ``None`` only when zero M15 history has ever been retained (the very
    first cycles). The caller (``ProductionAdvisoryComposer``) is
    responsible for forcing this to ``None`` alongside
    ``technical``/``m15_market_structure`` whenever the current cycle's own
    Technical contour was safety-discarded for a fetch failure - this field
    alone never distinguishes "fresh" from "stale-but-retained" for that
    decision (see the composer's own discard policy)."""

    technical: TechnicalSupervisorResult
    m15_market_structure: MarketStructureFeatures
    m15_last_closed_close: Decimal | None
    fetch_failures: tuple[TechnicalFetchFailure, ...]


class TechnicalProductionComposer:
    """Owns one long-lived ``TechnicalFeatureEngine`` and composes the
    current production ``TechnicalProductionResult`` from real Binance
    Futures OHLCV.

    The Futures OHLCV provider is always injected: this composer never
    constructs, owns or closes a ``BinanceRestClient`` - that lifecycle
    belongs to whatever process composition (Stage 0D) wires this composer
    together with Stage 0A's Flow bootstrap, so the two can share one
    Futures REST client. ``TechnicalFeatureEngine`` has no close lifecycle
    of its own, so this composer needs none either.
    """

    def __init__(
        self,
        *,
        config: TechnicalProductionConfig,
        provider: FuturesMarketDataProvider,
        engine: TechnicalFeatureEngine | None = None,
        supervisor: TechnicalSupervisor | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._engine = engine if engine is not None else TechnicalFeatureEngine()
        self._supervisor = supervisor if supervisor is not None else TechnicalSupervisor()

    def build_technical_result(self, *, as_of: Timestamp) -> TechnicalProductionResult:
        """Refresh every default timeframe from a fresh REST fetch, then
        build the current production ``TechnicalProductionResult`` from
        whatever real history is retained afterward.

        Always builds exactly six ``TechnicalFeatureSnapshot``s and runs
        exactly 42 analyst calls, even when one or more REST fetches fail -
        a fetch failure for one timeframe never removes that timeframe's
        seven supervisor cells; it only prevents new candles from being
        recorded for it this cycle, leaving existing retained history (which
        may be empty) completely untouched. ``as_of`` is used, unchanged and
        identical, for every one of the six snapshots - never the wall
        clock, never a per-timeframe value.
        """
        symbol = self._config.symbol
        contract_type = self._config.contract_type

        results = []
        fetch_failures: list[TechnicalFetchFailure] = []
        m15_snapshot = None
        m15_last_closed_close: Decimal | None = None

        for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
            try:
                candles = self._provider.get_ohlcv(symbol, timeframe, limit=TECHNICAL_OHLCV_FETCH_LIMIT)
            except MarketDataError as exc:
                fetch_failures.append(TechnicalFetchFailure(timeframe=timeframe, error_type=type(exc).__name__))
            else:
                closed, _forming = split_closed_and_forming(candles, timeframe, as_of)
                history = self._engine.history_for(symbol, contract_type, timeframe)
                existing_timestamps = {candle.timestamp for candle in history.candles.latest()}
                new_closed = [candle for candle in closed if candle.timestamp not in existing_timestamps]
                if new_closed:
                    self._engine.record_candles(symbol, contract_type, timeframe, new_closed)

            snapshot = self._engine.build_snapshot(
                symbol=symbol,
                contract_type=contract_type,
                timeframe=timeframe,
                as_of=as_of,
            )
            if timeframe is Timeframe.M15:
                m15_snapshot = snapshot
                # Read AFTER record_candles above, so a successful fetch this
                # cycle is reflected immediately - never the forming candle,
                # never an extra REST call (the retained store already holds
                # exactly what this cycle's own closed-candle processing just
                # produced, or whatever was already retained on a fetch
                # failure for this timeframe).
                m15_retained = self._engine.history_for(symbol, contract_type, Timeframe.M15).candles.latest()
                m15_last_closed_close = m15_retained[-1].close if m15_retained else None

            for analyst in _ANALYSTS:
                results.append(analyst.analyze(snapshot))

        assert m15_snapshot is not None  # guaranteed: DEFAULT_TECHNICAL_TIMEFRAMES always includes Timeframe.M15

        technical = self._supervisor.aggregate(results)
        return TechnicalProductionResult(
            technical=technical,
            m15_market_structure=m15_snapshot.market_structure,
            m15_last_closed_close=m15_last_closed_close,
            fetch_failures=tuple(fetch_failures),
        )


__all__ = [
    "TECHNICAL_OHLCV_FETCH_LIMIT",
    "TechnicalFetchFailure",
    "TechnicalProductionComposer",
    "TechnicalProductionConfig",
    "TechnicalProductionResult",
]
