"""Full end-to-end ACTIONABLE advisory-cycle proof (post-migration audit,
MT5 Price Authority migration).

Existing composer-level tests (``tests/test_production_advisory_composer.py``,
``tests/test_production_advisory_mt5_lifecycle.py``) only ever inject a
``FakeTechnicalComposer`` returning a sentinel ``object()`` as
``technical``/``m15_market_structure`` - so Judge/Policy/Setup
Construction/Risk/Portfolio/Session/Final Recommendation are never actually
exercised end-to-end through ``ProductionAdvisoryComposer.run_cycle`` there;
only composer-level plumbing (lifecycle, idempotency, wiring) is proven.
Full-pipeline ACTIONABLE construction is separately proven stage-by-stage
(e.g. ``tests/final_recommendation_support.py``/``tests/session_support.py``),
but never all the way through ``ProductionAdvisoryComposer.run_cycle`` into a
``RecommendationDTO``/``AdvisoryResponse``.

This module closes that gap: two full cycles through the REAL, unmodified
``ProductionAdvisoryComposer.run_cycle`` - one producing an ACTIONABLE LONG
TREND_FOLLOWING recommendation, one producing an ACTIONABLE SHORT
TREND_FOLLOWING recommendation - injected only at the composer's own
already-approved constructor DI seams (``flow_bootstrap``,
``technical_composer``, ``mt5_client``, ``rollover_persistence``,
``tracking_persistence``, ``provenance_persistence``). Judge/Policy/Setup
Construction/Risk/Portfolio/Session/Final Recommendation all run for real,
unmodified, driven only by realistic injected MT5/technical data.

Note on a corrected assumption (see this task's own audit trail): a LOW/HIGH
swing FAR from the current MT5 quote (e.g. price 90 for a ~100 entry, as in
``tests.decision_risk_pipeline_support.trend_following_market_structure`` -
deliberately far, for Part C's own risk-arithmetic tests) produces a huge
``risk_per_unit`` that Stage 10C's own broker-volume floor rejects
(``MT5SizingOutcome.BELOW_BROKER_MINIMUM_VOLUME`` - see
``tests/test_final_recommendation.py::test_non_actionable_stage_10c_blocks_recommendation``,
which uses that exact "far" fixture to prove precisely this BLOCKED path).
Reaching a genuine ``FinalRecommendationVerdict.ACTIONABLE`` end-to-end
requires a swing CLOSE to the current MT5 quote, mirroring
``tests.final_recommendation_support.actionable_trend_market_structure``'s own
close-swing design. This was verified empirically (a throwaway script driving
``run_runtime_cycle`` directly with this file's exact fixtures) before this
suite was written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.application.advisory_service import map_advisory_response
from app.application.dto import ApplicationAdvisoryStatus
from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.enums.trade import TradeDirection
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.mt5.persistence import MT5RolloverStatePersistence
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.config import SymbolMapping
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from app.technical.production import TechnicalProductionResult
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.market_evaluation_support import CONTRACT_TYPE as BINANCE_CONTRACT_TYPE
from tests.market_evaluation_support import SYMBOL as BINANCE_SYMBOL
from tests.market_evaluation_support import full_flow_result, full_technical_result
from tests.production_advisory_support import AS_OF, FakeRecordPersistence, all_trade_ids, build_config
from tests.runtime_cycle_support import RuntimeCycleFakeClient, default_account_facts
from tests.setup_construction_support import swing, symbol_facts as build_symbol_facts, usable_market_structure
from tests.technical_supervisor_support import DEFAULT_ANALYSTS, DEFAULT_TIMEFRAMES, analyzed_result, make_observation

MT5_SYMBOL = "BTCUSDt"
LOGICAL_SYMBOL = "BTC"

# A swing CLOSE to the current MT5 quote (bid=100/ask=100.10 - see
# ``symbol_facts()`` below) - not the "far" (90/110) fixture used elsewhere
# for Part C's own risk-arithmetic (never-reaches-sizing) tests. See this
# module's own docstring for why the far fixture would never reach ACTIONABLE.
LONG_STOP_PRICE = Decimal("100")
SHORT_STOP_PRICE = Decimal("100.10")

_BEARISH_OBSERVATION_OVERRIDES: dict[TechnicalAnalystType, tuple[TechnicalAnalysisDimension, str]] = {
    TechnicalAnalystType.TREND: (TechnicalAnalysisDimension.RETURN_DIRECTION, "DOWNWARD"),
    TechnicalAnalystType.MOMENTUM: (TechnicalAnalysisDimension.ROC_SIGN, "NEGATIVE"),
    TechnicalAnalystType.MOVING_AVERAGE: (TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, "BELOW_SMA"),
}
"""Bearish flip of ``tests.technical_supervisor_support._DEFAULT_OBSERVATION``
for exactly the three directional dimensions - MARKET_STRUCTURE stays
NO_BREAK_CONFIRMED (unchanged: TREND_FOLLOWING's own stop selector reads
``m15_market_structure`` swings directly, never this dimension), and
VOLATILITY/CANDLE_STRUCTURE/RANGE_STATE stay at their directionally-neutral
defaults."""


def symbol_facts(**overrides: object):
    fields: dict[str, object] = {"symbol": MT5_SYMBOL, "bid": Decimal("100"), "ask": Decimal("100.10")}
    fields.update(overrides)
    return build_symbol_facts(**fields)


def bearish_technical_result():
    """Full 7-analyst x 6-timeframe matrix, bearish-flipped on exactly the
    three directional dimensions - the mirror image of
    ``tests.market_evaluation_support.full_technical_result`` (already
    bullish: TREND=UPWARD, MOMENTUM=POSITIVE, MOVING_AVERAGE=ABOVE_SMA,
    MARKET_STRUCTURE=NO_BREAK_CONFIRMED)."""

    def one_result(analyst_type, timeframe):
        override = _BEARISH_OBSERVATION_OVERRIDES.get(analyst_type)
        if override is None:
            return analyzed_result(analyst_type, timeframe)
        dimension, value = override
        subject = "20" if analyst_type is TechnicalAnalystType.MOVING_AVERAGE else None
        return analyzed_result(
            analyst_type, timeframe, observations=(make_observation(dimension=dimension, value=value, subject=subject),)
        )

    results = tuple(one_result(analyst, timeframe) for timeframe in DEFAULT_TIMEFRAMES for analyst in DEFAULT_ANALYSTS)
    return TechnicalSupervisor().aggregate(results)


class RealFlowBootstrap:
    """Mirrors ``tests.production_advisory_support.FakeFlowBootstrap``'s
    start/stop/health surface exactly, but ``build_flow_result`` returns a
    REAL, non-sentinel ``FlowSupervisorResult`` (``full_flow_result()``)
    instead of ``None`` - so Stage 5 Market Evaluation sees genuine Flow
    evidence too, never just Technical."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.build_calls: list[object] = []

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    def build_flow_result(self, *, as_of: object):
        self.build_calls.append(as_of)
        return full_flow_result(symbol=BINANCE_SYMBOL, contract_type=BINANCE_CONTRACT_TYPE)

    def health(self):
        from app.core.models.stream_health import StreamHealth
        from app.flow.open_interest_poller import TaskHealth, TaskState
        from app.flow.realtime_bootstrap import FlowRealtimeBootstrapHealth

        now = datetime.now(UTC)
        stream = StreamHealth(provider="fake", stream="market", status="CONNECTED", checked_at=now)
        task = TaskHealth(state=TaskState.RUNNING)
        return FlowRealtimeBootstrapHealth(
            market=stream,
            order_book=stream,
            open_interest_last_attempt_at=None,
            open_interest_last_success_at=None,
            market_transport_task=task,
            public_transport_task=task,
            trades_task=task,
            liquidations_task=task,
            order_book_task=task,
            funding_task=task,
            funding_cache_refresh_task=task,
            open_interest_task=task,
        )


class RealTechnicalComposer:
    """Mirrors ``tests.production_advisory_support.FakeTechnicalComposer``'s
    surface, but returns REAL, non-sentinel ``technical``/
    ``m15_market_structure`` payloads instead of ``object()`` sentinels - the
    one seam this module exists to exercise."""

    def __init__(self, *, technical: object, m15_market_structure: object) -> None:
        self._technical = technical
        self._m15_market_structure = m15_market_structure
        self.build_calls: list[object] = []

    def build_technical_result(self, *, as_of: object) -> TechnicalProductionResult:
        self.build_calls.append(as_of)
        return TechnicalProductionResult(
            technical=self._technical,  # type: ignore[arg-type]
            m15_market_structure=self._m15_market_structure,  # type: ignore[arg-type]
            fetch_failures=(),
        )


def _build_composer(
    *, tmp_path: Path, technical: object, m15_market_structure: object, mt5_symbol: str = MT5_SYMBOL
) -> tuple[ProductionAdvisoryComposer, RuntimeCycleFakeClient, FakeRecordPersistence, FakeRecordPersistence]:
    mapping = SymbolMapping(logical_symbol=LOGICAL_SYMBOL, binance_symbol=BINANCE_SYMBOL, mt5_symbol=mt5_symbol)
    config = build_config(
        symbol_mapping=mapping,
        contract_type=BINANCE_CONTRACT_TYPE,
        market=MarketType.CRYPTO,
        rollover_state_path=tmp_path / "rollover.json",
        tracking_directory=tmp_path / "tracking",
        provenance_directory=tmp_path / "provenance",
        calendar_bridge_path=tmp_path / "calendar_absent.json",
    )

    client = RuntimeCycleFakeClient(
        runtime_status=MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.AVAILABLE),
        account_facts=default_account_facts(as_of=AS_OF),
        positions_result=("OK", ()),
        history_deals_result=("OK", ()),
        symbol_facts_by_symbol={mt5_symbol: symbol_facts(symbol=mt5_symbol, as_of=AS_OF)},
    )

    tracking_persistence = FakeRecordPersistence()
    provenance_persistence = FakeRecordPersistence()
    rollover_persistence = MT5RolloverStatePersistence(tmp_path / "rollover.json")

    composer = ProductionAdvisoryComposer(
        config=config,
        flow_bootstrap=RealFlowBootstrap(),
        technical_composer=RealTechnicalComposer(technical=technical, m15_market_structure=m15_market_structure),
        mt5_client=client,
        rollover_persistence=rollover_persistence,
        tracking_persistence=tracking_persistence,
        provenance_persistence=provenance_persistence,
    )
    return composer, client, tracking_persistence, provenance_persistence


def _trend_following_result(runtime_cycle_result):
    final_construction = runtime_cycle_result.final_recommendation_construction_result
    assert final_construction is not None
    matches = [r for r in final_construction.family_results if r.family is StrategyFamily.TREND_FOLLOWING]
    assert len(matches) == 1
    return matches[0]


# --------------------------------------------------------------------------- #
# LONG
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_full_cycle_produces_actionable_long_recommendation(tmp_path: Path) -> None:
    technical = full_technical_result(symbol=BINANCE_SYMBOL, contract_type=BINANCE_CONTRACT_TYPE)
    m15_market_structure = usable_market_structure(
        swings=(swing(kind=SwingKind.LOW, price=LONG_STOP_PRICE),), symbol=MT5_SYMBOL
    )
    composer, client, tracking_persistence, _provenance_persistence = _build_composer(
        tmp_path=tmp_path, technical=technical, m15_market_structure=m15_market_structure
    )
    facts = symbol_facts(as_of=AS_OF)

    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    # 1. Cycle outcome is READY, never SERVICE_UNAVAILABLE.
    assert result.outcome is ProductionAdvisoryCycleOutcome.READY

    # 2. TREND_FOLLOWING reached ACTIONABLE through the real pipeline.
    family_result = _trend_following_result(result.runtime_cycle_result)
    assert family_result.verdict is FinalRecommendationVerdict.ACTIONABLE
    recommendation = family_result.recommendation
    assert recommendation is not None

    # 3. Direction is LONG.
    assert recommendation.direction is TradeDirection.LONG

    # 4. Entry price is the MT5 ask (LONG's own resolution rule).
    assert recommendation.entry_price == facts.ask == Decimal("100.10")

    # 5. Stop below entry, equal to the tick-normalized swing price (100 -
    # already tick-aligned at trade_tick_size=0.00001, so unchanged).
    assert recommendation.stop_loss < recommendation.entry_price
    assert recommendation.stop_loss == LONG_STOP_PRICE == Decimal("100")

    # 6. Symbol is the MT5 broker-facing symbol, never logical/Binance.
    assert recommendation.symbol == MT5_SYMBOL
    assert recommendation.symbol != LOGICAL_SYMBOL
    assert recommendation.symbol != BINANCE_SYMBOL

    # 7. Application-layer mapping.
    advisory_response = map_advisory_response(logical_cycle_id="test-cycle", cycle=result)
    assert advisory_response.symbol == LOGICAL_SYMBOL
    assert advisory_response.status is ApplicationAdvisoryStatus.READY
    trend_dtos = [r for r in advisory_response.recommendations if r.strategy_family is StrategyFamily.TREND_FOLLOWING]
    assert len(trend_dtos) == 1
    assert trend_dtos[0].symbol == MT5_SYMBOL

    # 8. Tracking persistence received a write for TREND_FOLLOWING's trade_id.
    trend_trade_id = all_trade_ids()[StrategyFamily.TREND_FOLLOWING]
    written_trade_ids = [trade_id for trade_id, _value in tracking_persistence.write_calls]
    assert trend_trade_id in written_trade_ids

    # 9. Geometry/no-cross-venue proof: every numeric fact traces to MT5-native
    # symbol_facts/m15_market_structure, never to full_flow_result()/Binance.
    entry_source = facts.ask  # MT5 fact
    structural_stop_source = LONG_STOP_PRICE  # MT5-native m15 swing price
    normalized_stop = recommendation.stop_loss  # post tick-rounding value
    risk_distance = abs(recommendation.entry_price - recommendation.stop_loss)
    broker_protective_distance = facts.bid - recommendation.stop_loss  # LONG: measured from bid, per _broker_stop_distance
    assert recommendation.entry_price == entry_source
    assert normalized_stop == structural_stop_source
    assert risk_distance == Decimal("0.10")
    assert broker_protective_distance >= 0  # trivial: trade_stops_level=0
    assert recommendation.approved_volume is not None
    assert recommendation.approved_volume > 0
    assert recommendation.approved_volume == Decimal("0.05")
    # None of entry/stop/risk/volume matches anything full_flow_result() could
    # have produced - Flow carries no price/structure fact of this shape at
    # all (FlowSupervisorResult has no entry/stop/volume field whatsoever).

    # 10. MT5 connection lifecycle: exactly one initialize/shutdown pair.
    assert client.initialize_calls == 1
    assert client.shutdown_calls == 1


# --------------------------------------------------------------------------- #
# SHORT
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_full_cycle_produces_actionable_short_recommendation(tmp_path: Path) -> None:
    technical = bearish_technical_result()
    m15_market_structure = usable_market_structure(
        swings=(swing(kind=SwingKind.HIGH, price=SHORT_STOP_PRICE),), symbol=MT5_SYMBOL
    )
    composer, client, tracking_persistence, _provenance_persistence = _build_composer(
        tmp_path=tmp_path, technical=technical, m15_market_structure=m15_market_structure
    )
    facts = symbol_facts(as_of=AS_OF)

    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    # 1. Cycle outcome is READY, never SERVICE_UNAVAILABLE.
    assert result.outcome is ProductionAdvisoryCycleOutcome.READY

    # 2. TREND_FOLLOWING reached ACTIONABLE through the real pipeline.
    family_result = _trend_following_result(result.runtime_cycle_result)
    assert family_result.verdict is FinalRecommendationVerdict.ACTIONABLE
    recommendation = family_result.recommendation
    assert recommendation is not None

    # 3. Direction is SHORT.
    assert recommendation.direction is TradeDirection.SHORT

    # 4. Entry price is the MT5 bid (SHORT's own resolution rule).
    assert recommendation.entry_price == facts.bid == Decimal("100")

    # 5. Stop above entry, equal to the tick-normalized swing price (100.10 -
    # already tick-aligned, so unchanged).
    assert recommendation.stop_loss > recommendation.entry_price
    assert recommendation.stop_loss == SHORT_STOP_PRICE == Decimal("100.10")

    # 6. Symbol is the MT5 broker-facing symbol, never logical/Binance.
    assert recommendation.symbol == MT5_SYMBOL
    assert recommendation.symbol != LOGICAL_SYMBOL
    assert recommendation.symbol != BINANCE_SYMBOL

    # 7. Application-layer mapping.
    advisory_response = map_advisory_response(logical_cycle_id="test-cycle", cycle=result)
    assert advisory_response.symbol == LOGICAL_SYMBOL
    assert advisory_response.status is ApplicationAdvisoryStatus.READY
    trend_dtos = [r for r in advisory_response.recommendations if r.strategy_family is StrategyFamily.TREND_FOLLOWING]
    assert len(trend_dtos) == 1
    assert trend_dtos[0].symbol == MT5_SYMBOL

    # 8. Tracking persistence received a write for TREND_FOLLOWING's trade_id.
    trend_trade_id = all_trade_ids()[StrategyFamily.TREND_FOLLOWING]
    written_trade_ids = [trade_id for trade_id, _value in tracking_persistence.write_calls]
    assert trend_trade_id in written_trade_ids

    # 9. Geometry/no-cross-venue proof: every numeric fact traces to MT5-native
    # symbol_facts/m15_market_structure, never to full_flow_result()/Binance.
    entry_source = facts.bid  # MT5 fact
    structural_stop_source = SHORT_STOP_PRICE  # MT5-native m15 swing price
    normalized_stop = recommendation.stop_loss  # post tick-rounding value
    risk_distance = abs(recommendation.entry_price - recommendation.stop_loss)
    broker_protective_distance = recommendation.stop_loss - facts.ask  # SHORT: measured from ask, per _broker_stop_distance
    assert recommendation.entry_price == entry_source
    assert normalized_stop == structural_stop_source
    assert risk_distance == Decimal("0.10")
    assert broker_protective_distance >= 0  # trivial: trade_stops_level=0
    assert recommendation.approved_volume is not None
    assert recommendation.approved_volume > 0
    assert recommendation.approved_volume == Decimal("0.05")

    # 10. MT5 connection lifecycle: exactly one initialize/shutdown pair.
    assert client.initialize_calls == 1
    assert client.shutdown_calls == 1


# --------------------------------------------------------------------------- #
# Duplicate-cycle rejection: zero MT5 provider side effects
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_cycle_rejection_never_touches_mt5(tmp_path: Path) -> None:
    """A collision on ANY supplied trade_id must refuse the whole cycle
    before ``self._mt5_client.initialize()`` is ever called - the preflight
    (``ProductionAdvisoryComposer._reject_if_duplicate_cycle``) runs strictly
    before the ``try/finally`` MT5 connection-lifecycle block in ``run_cycle``
    (see ``app/production_advisory/composer.py``). Uses
    ``RuntimeCycleFakeClient`` (which tracks ``initialize_calls`` - unlike
    ``tests.production_advisory_support.FakeMT5Client``, the stateless double
    ``test_production_advisory_idempotency.py`` uses, which does not track
    call counts at all) to prove this call is never even attempted."""
    technical = full_technical_result(symbol=BINANCE_SYMBOL, contract_type=BINANCE_CONTRACT_TYPE)
    m15_market_structure = usable_market_structure(
        swings=(swing(kind=SwingKind.LOW, price=LONG_STOP_PRICE),), symbol=MT5_SYMBOL
    )
    composer, client, tracking_persistence, _provenance_persistence = _build_composer(
        tmp_path=tmp_path, technical=technical, m15_market_structure=m15_market_structure
    )
    trade_ids = all_trade_ids()
    # Pre-seed tracking so one family's trade_id already reads non-"ABSENT".
    tracking_persistence.write(trade_ids[StrategyFamily.TREND_FOLLOWING], "prior record")

    await composer.startup()
    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_info:
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert trade_ids[StrategyFamily.TREND_FOLLOWING] in exc_info.value.colliding_trade_ids
    assert client.initialize_calls == 0
    assert client.shutdown_calls == 0


# --------------------------------------------------------------------------- #
# PROVIDER-AWARE SYMBOL SCOPE regression: deliberately non-colliding
# binance_symbol/mt5_symbol pair (corrective review, "PROVIDER-AWARE SYMBOL
# SCOPE VALIDATION")
# --------------------------------------------------------------------------- #

NONCOLLIDING_MT5_SYMBOL = "BTCUSD.m"
"""Deliberately does NOT collide with BINANCE_SYMBOL under uppercasing:
``"BTCUSD.m".upper() == "BTCUSD.M" != "BTCUSDT"`` - unlike this file's own
module-level ``MT5_SYMBOL = "BTCUSDt"``, whose uppercase form happens to
equal ``BINANCE_SYMBOL`` by coincidence. Proves the full production
composition still reaches ACTIONABLE end-to-end (through the real,
unmodified Market Evaluation scope check) once that coincidence is removed -
this would have raised ``ScopeMismatchError`` under the pre-fix
``technical.symbol == context.symbol`` invariant."""


@pytest.mark.asyncio
async def test_full_cycle_with_noncolliding_mt5_symbol_still_reaches_actionable(tmp_path: Path) -> None:
    technical = full_technical_result(symbol=NONCOLLIDING_MT5_SYMBOL, contract_type=BINANCE_CONTRACT_TYPE)
    m15_market_structure = usable_market_structure(
        swings=(swing(kind=SwingKind.LOW, price=LONG_STOP_PRICE),), symbol=NONCOLLIDING_MT5_SYMBOL
    )
    composer, client, tracking_persistence, _provenance_persistence = _build_composer(
        tmp_path=tmp_path, technical=technical, m15_market_structure=m15_market_structure, mt5_symbol=NONCOLLIDING_MT5_SYMBOL
    )
    facts = symbol_facts(symbol=NONCOLLIDING_MT5_SYMBOL, as_of=AS_OF)

    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    # 1. Cycle outcome is READY - Market Evaluation did NOT reject this
    # cross-provider pair, even though "BTCUSD.m".upper() != "BTCUSDT".
    assert result.outcome is ProductionAdvisoryCycleOutcome.READY

    # 2. TREND_FOLLOWING still reached ACTIONABLE through the real pipeline.
    family_result = _trend_following_result(result.runtime_cycle_result)
    assert family_result.verdict is FinalRecommendationVerdict.ACTIONABLE
    recommendation = family_result.recommendation
    assert recommendation is not None

    # 3. Setup Construction received exactly the MT5 symbol, never Binance/logical.
    assert recommendation.symbol == NONCOLLIDING_MT5_SYMBOL
    assert recommendation.symbol != BINANCE_SYMBOL
    assert recommendation.symbol != LOGICAL_SYMBOL

    # 4. Risk/sizing called client.symbol_facts() for exactly this MT5 symbol.
    assert NONCOLLIDING_MT5_SYMBOL in client.symbol_facts_calls

    # 5. RecommendationDTO preserves the exact MT5 symbol.
    advisory_response = map_advisory_response(logical_cycle_id="test-cycle-noncolliding", cycle=result)
    trend_dtos = [r for r in advisory_response.recommendations if r.strategy_family is StrategyFamily.TREND_FOLLOWING]
    assert len(trend_dtos) == 1
    assert trend_dtos[0].symbol == NONCOLLIDING_MT5_SYMBOL

    # 6. AdvisoryResponse preserves the logical BTC identity, unaffected.
    assert advisory_response.symbol == LOGICAL_SYMBOL

    # 7. Entry/stop geometry remains MT5-native (no cross-venue price), unaffected
    # by the symbol change.
    assert recommendation.entry_price == facts.ask == Decimal("100.10")
    assert recommendation.stop_loss == LONG_STOP_PRICE == Decimal("100")

    # 8. Tracking persistence still received the write for TREND_FOLLOWING's trade_id.
    trend_trade_id = all_trade_ids()[StrategyFamily.TREND_FOLLOWING]
    written_trade_ids = [trade_id for trade_id, _value in tracking_persistence.write_calls]
    assert trend_trade_id in written_trade_ids

    # 9. MT5 connection lifecycle unaffected: exactly one initialize/shutdown pair.
    assert client.initialize_calls == 1
    assert client.shutdown_calls == 1
