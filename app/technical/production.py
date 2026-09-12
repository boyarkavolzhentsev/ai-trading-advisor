"""Stage 0B/MT5 Price Authority Stage B Technical production wiring: real
OHLCV from an injected, provider-agnostic ``OHLCVProvider`` -> the
existing, unmodified ``TechnicalFeatureEngine`` -> the existing, unmodified
seven Stage 3B analysts -> the existing, unmodified ``TechnicalSupervisor``.

``TechnicalProductionComposer`` owns exactly one configured ``(symbol,
contract_type)`` pair's long-lived ``TechnicalFeatureEngine`` and, on every
call to ``build_technical_result``, refreshes every configured timeframe
(``DEFAULT_TECHNICAL_TIMEFRAMES`` unless the caller injects a different
preset, e.g. the MT5 V1 timeframe set) from a fresh fetch before composing
the current production ``TechnicalSupervisorResult``. It owns no
trading/decision logic of any kind - no Market Evaluation, Strategy Router,
Judge, Policy, Risk, Diversification, Statistics/Session, MT5, LLM, or
bot/HTTP delivery dependency exists here (enforced by
``tests/test_technical_production_module_hygiene.py``), and it never
combines this result with Flow evidence of any kind.

Provider-agnostic by design (MT5 Price Authority Stage B contract
correction): every timeframe fetch is a plain, sequential call to an
injected ``OHLCVProvider`` - no provider-specific import, no
``isinstance`` branching, no WebSocket, no background task, no
``asyncio`` anywhere in this module (enforced by
``tests/test_technical_no_mt5_provider_coupling.py``). The same
authoritative cycle ``as_of`` is passed to every one of those calls -
a native-timeframe provider (e.g. Binance) is free to ignore it, while a
provider that must derive a timeframe internally (e.g. MT5 synthesizing
H4) relies on it for deterministic closed/forming classification. A fetch
failure for one timeframe never removes that timeframe's analyst cells from
the eventual matrix: this composer always builds one
``TechnicalFeatureSnapshot`` per configured timeframe and always runs all
seven analysts against each one, feeding whatever history is currently
retained (including empty history) through unchanged. Data insufficiency
therefore surfaces only through ``FeatureStatus``/``FeatureQuality`` and
analyst abstention - ``TechnicalSupervisorResult.missing_cells`` stays
empty under ordinary provider degradation - never through an omitted
composition cell.

Only ``app.market_data.exceptions.MarketDataError`` is treated as ordinary,
expected provider degradation; every other exception (a Stage 3A ingestion
error, a Stage 3C supervisor invariant error, or any programming defect
from a provider/analyst) is left to propagate uncaught, mirroring Stage
0A's own established convention for distinguishing legitimate market
conditions from genuine bugs.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.market_data.exceptions import MarketDataError
from app.market_data.protocols import OHLCVProvider
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
    """Narrow Stage 0B production result: the full ``TechnicalSupervisorResult``
    plus the one M15 market-structure fact Setup Construction needs, reused
    verbatim from the same M15 snapshot - never recomputed and never
    ``Optional`` (this composer always builds one snapshot per configured
    timeframe including M15, and ``compute_market_structure_features``
    always returns a populated object, carrying ``UNAVAILABLE`` quality on
    empty history rather than being omitted). Carries no raw per-timeframe
    snapshot and no trading decision field of any kind.

    Deliberately carries no standalone M15 reference-price field as of MT5
    Price Authority Stage C: that field existed solely to bridge an M15
    close into the now-fully-retired cross-venue price-basis reconciliation
    layer (``app.decision.setup_construction``) - Setup Construction is now
    MT5-native throughout and needs only ``m15_market_structure`` itself."""

    technical: TechnicalSupervisorResult
    m15_market_structure: MarketStructureFeatures
    fetch_failures: tuple[TechnicalFetchFailure, ...]


class TechnicalProductionComposer:
    """Owns one long-lived ``TechnicalFeatureEngine`` and composes the
    current production ``TechnicalProductionResult`` from real OHLCV
    served by an injected, provider-agnostic ``OHLCVProvider``.

    The OHLCV provider is always injected: this composer never constructs,
    owns or closes any provider's underlying transport (a
    ``BinanceRestClient``, an ``MT5Client``, or anything else) - that
    lifecycle belongs to whatever process composition (Stage 0D) wires this
    composer together with the rest of production. ``TechnicalFeatureEngine``
    has no close lifecycle of its own, so this composer needs none either.
    """

    def __init__(
        self,
        *,
        config: TechnicalProductionConfig,
        provider: OHLCVProvider,
        timeframes: tuple[Timeframe, ...] = DEFAULT_TECHNICAL_TIMEFRAMES,
        engine: TechnicalFeatureEngine | None = None,
        supervisor: TechnicalSupervisor | None = None,
    ) -> None:
        if Timeframe.M15 not in timeframes:
            raise ValueError(
                "timeframes must include Timeframe.M15 - m15_market_structure is required "
                "downstream by Setup Construction"
            )
        self._config = config
        self._provider = provider
        self._timeframes = timeframes
        self._engine = engine if engine is not None else TechnicalFeatureEngine()
        self._supervisor = (
            supervisor if supervisor is not None else TechnicalSupervisor(expected_timeframes=self._timeframes)
        )

    def build_technical_result(self, *, as_of: Timestamp) -> TechnicalProductionResult:
        """Refresh every configured timeframe from a fresh fetch, then build
        the current production ``TechnicalProductionResult`` from whatever
        real history is retained afterward.

        Always builds exactly one ``TechnicalFeatureSnapshot`` per configured
        timeframe and runs all seven analysts against each, even when one or
        more fetches fail - a fetch failure for one timeframe never removes
        that timeframe's seven supervisor cells; it only prevents new candles
        from being recorded for it this cycle, leaving existing retained
        history (which may be empty) completely untouched. ``as_of`` is used,
        unchanged and identical, for every one of these snapshots AND passed
        to every ``provider.get_ohlcv`` call - never the wall clock, never a
        per-timeframe value.
        """
        symbol = self._config.symbol
        contract_type = self._config.contract_type

        results = []
        fetch_failures: list[TechnicalFetchFailure] = []
        m15_snapshot = None

        for timeframe in self._timeframes:
            try:
                candles = self._provider.get_ohlcv(
                    symbol, timeframe, limit=TECHNICAL_OHLCV_FETCH_LIMIT, as_of=as_of
                )
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

            for analyst in _ANALYSTS:
                results.append(analyst.analyze(snapshot))

        assert m15_snapshot is not None  # guaranteed: __init__ rejects any timeframes without Timeframe.M15

        technical = self._supervisor.aggregate(results)
        return TechnicalProductionResult(
            technical=technical,
            m15_market_structure=m15_snapshot.market_structure,
            fetch_failures=tuple(fetch_failures),
        )


__all__ = [
    "TECHNICAL_OHLCV_FETCH_LIMIT",
    "TechnicalFetchFailure",
    "TechnicalProductionComposer",
    "TechnicalProductionConfig",
    "TechnicalProductionResult",
]
