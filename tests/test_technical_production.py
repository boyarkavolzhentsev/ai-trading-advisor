"""Stage 0B Technical production composer: happy-path and repeated-cycle
behaviour against a fake, in-process Futures OHLCV provider and the real,
unmodified ``TechnicalFeatureEngine``/analysts/``TechnicalSupervisor``. No
real network access happens anywhere in this file.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical.engine import TechnicalFeatureEngine
from app.technical.production import (
    TECHNICAL_OHLCV_FETCH_LIMIT,
    TechnicalProductionComposer,
    TechnicalProductionConfig,
)
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES
from app.technical_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS
from tests.technical_production_support import (
    CONTRACT_TYPE,
    NOW,
    SYMBOL,
    FakeFuturesOHLCVProvider,
    make_candles,
    make_config,
)


class _SpyEngine(TechnicalFeatureEngine):
    """Records every ``build_snapshot`` call's timeframe and result, without
    altering any behaviour - a pure observation seam, never a modification
    of ``TechnicalFeatureEngine``."""

    def __init__(self) -> None:
        super().__init__()
        self.build_snapshot_calls: list[Timeframe] = []
        self.snapshots_by_timeframe: dict[Timeframe, TechnicalFeatureSnapshot] = {}

    def build_snapshot(self, **kwargs: object) -> TechnicalFeatureSnapshot:
        timeframe = kwargs["timeframe"]
        assert isinstance(timeframe, Timeframe)
        self.build_snapshot_calls.append(timeframe)
        snapshot = super().build_snapshot(**kwargs)  # type: ignore[arg-type]
        self.snapshots_by_timeframe[timeframe] = snapshot
        return snapshot


def _fully_stocked_provider() -> FakeFuturesOHLCVProvider:
    provider = FakeFuturesOHLCVProvider()
    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(timeframe, make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW))
    return provider


# --------------------------------------------------------------------------- #
# config contract
# --------------------------------------------------------------------------- #


def test_config_carries_exactly_symbol_and_contract_type() -> None:
    config = TechnicalProductionConfig(symbol=SYMBOL, contract_type=CONTRACT_TYPE)
    assert config.symbol == SYMBOL
    assert config.contract_type is CONTRACT_TYPE


# --------------------------------------------------------------------------- #
# fetch order / input contract
# --------------------------------------------------------------------------- #


def test_all_six_timeframes_requested_in_canonical_order() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    composer.build_technical_result(as_of=NOW)

    assert [call[1] for call in provider.calls] == list(DEFAULT_TECHNICAL_TIMEFRAMES)


def test_every_fetch_uses_configured_symbol_and_limit_51() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(symbol="ETHUSDT"), provider=provider)

    composer.build_technical_result(as_of=NOW)

    assert TECHNICAL_OHLCV_FETCH_LIMIT == 51
    for symbol, _timeframe, limit in provider.calls:
        assert symbol == "ETHUSDT"
        assert limit == 51


def test_fetch_order_is_deterministic_across_repeated_calls() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    composer.build_technical_result(as_of=NOW)
    first_order = [call[1] for call in provider.calls]
    composer.build_technical_result(as_of=NOW + timedelta(minutes=1))
    second_order = [call[1] for call in provider.calls][len(first_order) :]

    assert first_order == second_order == list(DEFAULT_TECHNICAL_TIMEFRAMES)


# --------------------------------------------------------------------------- #
# as_of / snapshot semantics
# --------------------------------------------------------------------------- #


def test_same_caller_supplied_as_of_used_for_all_42_results() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert len(result.technical.analyst_results) == 42
    for analyst_result in result.technical.analyst_results:
        assert analyst_result.observation_time == NOW


def test_configured_contract_type_used_by_engine() -> None:
    provider = _fully_stocked_provider()
    engine = TechnicalFeatureEngine()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    composer.build_technical_result(as_of=NOW)

    history = engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M15)
    assert len(history.candles.latest()) > 0


# --------------------------------------------------------------------------- #
# 42-cell analyst matrix
# --------------------------------------------------------------------------- #


def test_produces_exactly_42_analyzed_cells_on_full_history() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.technical.expected_count == 42
    assert result.technical.analyzed_count == 42
    assert result.technical.missing_count == 0
    assert len(result.technical.analyst_results) == 42


def test_expected_analysts_match_supervisor_canonical_default() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert set(result.technical.expected_analysts) == set(DEFAULT_EXPECTED_ANALYSTS)
    assert set(result.technical.expected_timeframes) == set(DEFAULT_TECHNICAL_TIMEFRAMES)


# --------------------------------------------------------------------------- #
# forming-candle handling
# --------------------------------------------------------------------------- #


def test_forming_candle_never_recorded_into_engine_history() -> None:
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        candles = make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW)
        provider.set_response(timeframe, candles)
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    composer.build_technical_result(as_of=NOW)

    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        forming_open_time = make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW)[-1].timestamp
        retained_timestamps = {
            c.timestamp for c in engine.history_for(SYMBOL, CONTRACT_TYPE, timeframe).candles.latest()
        }
        assert forming_open_time not in retained_timestamps


def test_forming_candle_recorded_once_it_closes_on_a_later_cycle() -> None:
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    timeframe = Timeframe.M5
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    candles = make_candles(timeframe, 3, as_of=NOW)
    provider.set_response(timeframe, candles)
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    composer.build_technical_result(as_of=NOW)
    still_forming_timestamp = candles[-1].timestamp
    retained_after_cycle_1 = {
        c.timestamp for c in engine.history_for(SYMBOL, CONTRACT_TYPE, timeframe).candles.latest()
    }
    assert still_forming_timestamp not in retained_after_cycle_1

    later_as_of = NOW + timedelta(minutes=5)
    provider.set_response(timeframe, make_candles(timeframe, 4, as_of=later_as_of))
    composer.build_technical_result(as_of=later_as_of)
    retained_after_cycle_2 = {
        c.timestamp for c in engine.history_for(SYMBOL, CONTRACT_TYPE, timeframe).candles.latest()
    }
    assert still_forming_timestamp in retained_after_cycle_2


# --------------------------------------------------------------------------- #
# repeated-cycle dedup
# --------------------------------------------------------------------------- #


def test_first_cycle_records_all_closed_candles() -> None:
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    candles = make_candles(Timeframe.M5, 5, as_of=NOW)
    provider.set_response(Timeframe.M5, candles)
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    composer.build_technical_result(as_of=NOW)

    retained = engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest()
    assert len(retained) == 4  # 5 fetched, last one still forming as of NOW


def test_identical_second_cycle_does_not_duplicate_or_raise() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    composer.build_technical_result(as_of=NOW)
    before = len(composer._engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    composer.build_technical_result(as_of=NOW)  # identical fetch, identical as_of
    after = len(composer._engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    assert before == after


def test_one_new_closed_candle_is_recorded_once() -> None:
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, 5, as_of=NOW))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)
    composer.build_technical_result(as_of=NOW)
    before = len(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    next_as_of = NOW + timedelta(minutes=5)
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, 6, as_of=next_as_of))
    composer.build_technical_result(as_of=next_as_of)
    after = len(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    assert after == before + 1


def test_multiple_new_closed_candles_each_recorded_once() -> None:
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, 5, as_of=NOW))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)
    composer.build_technical_result(as_of=NOW)
    before = len(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    later_as_of = NOW + timedelta(minutes=15)  # 3 more 5m boundaries pass
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, 8, as_of=later_as_of))
    composer.build_technical_result(as_of=later_as_of)
    after = len(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())

    assert after == before + 3


def test_duplicate_rest_window_does_not_raise() -> None:
    provider = _fully_stocked_provider()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)
    composer.build_technical_result(as_of=NOW)

    # Same exact overlapping window fetched again - must not raise DuplicateCandleTimestampError.
    composer.build_technical_result(as_of=NOW)


def test_backfill_candle_older_than_newest_but_missing_is_inserted() -> None:
    """Reproduces the exact scenario required by the design: retained
    {10:00, 10:05, 10:15} (10:10 skipped by a prior failed fetch), a later
    fetch returns {10:10, 10:15, 10:20} - the composer must insert 10:10 and
    10:20 while filtering the duplicate 10:15, proving timestamp-set dedup
    rather than a `timestamp > last_known` filter.
    """
    from datetime import UTC, datetime
    from decimal import Decimal

    def candle(minute: int, close: Decimal) -> OHLCVCandle:
        return OHLCVCandle(
            timestamp=datetime(2026, 1, 2, 10, minute, tzinfo=UTC),
            open=close - Decimal("0.5"),
            high=close + 1,
            low=close - 1,
            close=close,
            volume=Decimal(10),
        )

    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    provider.set_response(
        Timeframe.M5, [candle(0, Decimal(100)), candle(5, Decimal(101)), candle(15, Decimal(103))]
    )
    composer.build_technical_result(as_of=datetime(2026, 1, 2, 10, 20, tzinfo=UTC))

    provider.set_response(
        Timeframe.M5, [candle(10, Decimal(102)), candle(15, Decimal(103)), candle(20, Decimal(104))]
    )
    composer.build_technical_result(as_of=datetime(2026, 1, 2, 10, 25, tzinfo=UTC))

    retained_timestamps = sorted(
        c.timestamp for c in engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest()
    )
    assert retained_timestamps == [
        datetime(2026, 1, 2, 10, minute, tzinfo=UTC) for minute in (0, 5, 10, 15, 20)
    ]


# --------------------------------------------------------------------------- #
# M15 single-build / reuse
# --------------------------------------------------------------------------- #


def test_m15_build_snapshot_invoked_exactly_once_per_cycle() -> None:
    provider = _fully_stocked_provider()
    spy_engine = _SpyEngine()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=spy_engine)

    composer.build_technical_result(as_of=NOW)

    assert spy_engine.build_snapshot_calls.count(Timeframe.M15) == 1
    assert len(spy_engine.build_snapshot_calls) == len(DEFAULT_TECHNICAL_TIMEFRAMES)


def test_m15_market_structure_is_exact_object_from_single_m15_snapshot() -> None:
    provider = _fully_stocked_provider()
    spy_engine = _SpyEngine()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=spy_engine)

    result = composer.build_technical_result(as_of=NOW)

    m15_snapshot = spy_engine.snapshots_by_timeframe[Timeframe.M15]
    assert result.m15_market_structure is m15_snapshot.market_structure


def test_m15_market_structure_non_optional_even_with_empty_history() -> None:
    from app.market_data.exceptions import ProviderUnavailableError

    provider = FakeFuturesOHLCVProvider()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.fail(tf, ProviderUnavailableError("down"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.m15_market_structure is not None
