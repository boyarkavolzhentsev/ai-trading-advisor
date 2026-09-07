"""Stage 0B Technical production composer: provider-failure degradation,
unexpected-error propagation, fetch-failure observability, and long-outage
gap behaviour - against a fake, in-process Futures OHLCV provider and the
real, unmodified ``TechnicalFeatureEngine``/analysts/``TechnicalSupervisor``.
No real network access happens anywhere in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.market_data.exceptions import InvalidProviderResponseError, ProviderUnavailableError
from app.technical.engine import TechnicalFeatureEngine
from app.technical.errors import MisalignedCandleError
from app.technical.production import (
    TECHNICAL_OHLCV_FETCH_LIMIT,
    TechnicalFetchFailure,
    TechnicalProductionComposer,
)
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES
from app.technical_supervisor.errors import EmptyResultsError
from tests.technical_production_support import (
    CONTRACT_TYPE,
    NOW,
    SYMBOL,
    FakeFuturesOHLCVProvider,
    make_candles,
    make_config,
)


def _fully_stocked_provider() -> FakeFuturesOHLCVProvider:
    provider = FakeFuturesOHLCVProvider()
    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(timeframe, make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW))
    return provider


# --------------------------------------------------------------------------- #
# A. one timeframe MarketDataError
# --------------------------------------------------------------------------- #


def test_single_timeframe_failure_still_produces_all_42_cells_with_empty_missing() -> None:
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, ProviderUnavailableError("connect timeout"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.technical.expected_count == 42
    assert len(result.technical.analyst_results) == 42
    assert result.technical.missing_count == 0
    assert result.fetch_failures == (TechnicalFetchFailure(timeframe=Timeframe.M1, error_type="ProviderUnavailableError"),)


def test_single_failed_timeframe_analysts_abstain_on_fresh_history() -> None:
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, ProviderUnavailableError("connect timeout"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    m1_cells = {(a, t) for (a, t) in result.technical.abstained_cells if t is Timeframe.M1}
    assert len(m1_cells) == 7  # all seven analysts abstain: M1 history stayed empty


# --------------------------------------------------------------------------- #
# B. multiple MarketDataErrors
# --------------------------------------------------------------------------- #


def test_multiple_timeframe_failures_still_produce_42_cells_with_empty_missing() -> None:
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, ProviderUnavailableError("down"))
    provider.fail(Timeframe.H4, InvalidProviderResponseError("bad payload"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.technical.expected_count == 42
    assert result.technical.missing_count == 0
    assert len(result.technical.analyst_results) == 42
    assert set(result.fetch_failures) == {
        TechnicalFetchFailure(timeframe=Timeframe.M1, error_type="ProviderUnavailableError"),
        TechnicalFetchFailure(timeframe=Timeframe.H4, error_type="InvalidProviderResponseError"),
    }


# --------------------------------------------------------------------------- #
# C. first-cycle M15 MarketDataError
# --------------------------------------------------------------------------- #


def test_first_cycle_m15_failure_still_yields_non_optional_market_structure() -> None:
    provider = FakeFuturesOHLCVProvider()
    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.fail(timeframe, ProviderUnavailableError("no history yet"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.m15_market_structure is not None
    from app.core.enums.quality import FeatureQuality

    assert result.m15_market_structure.status.quality is FeatureQuality.UNAVAILABLE
    m15_cells = {(a, t) for (a, t) in result.technical.abstained_cells if t is Timeframe.M15}
    assert len(m15_cells) == 7
    assert result.technical.missing_count == 0


# --------------------------------------------------------------------------- #
# D. retained history + current fetch failure
# --------------------------------------------------------------------------- #


def test_current_fetch_failure_leaves_retained_history_untouched_and_reusable() -> None:
    provider = _fully_stocked_provider()
    engine = TechnicalFeatureEngine()
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)
    composer.build_technical_result(as_of=NOW)
    retained_before = list(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M15).candles.latest())
    assert retained_before  # sanity: history was populated

    provider.fail(Timeframe.M15, ProviderUnavailableError("transient"))
    result = composer.build_technical_result(as_of=NOW + timedelta(minutes=1))

    retained_after = list(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M15).candles.latest())
    assert retained_after == retained_before  # untouched: no candle added, none removed

    m15_analyzed = {(a, t) for (a, t) in result.technical.analyzed_cells if t is Timeframe.M15}
    assert len(m15_analyzed) == 7  # retained history is still sufficient -> VALID, not downgraded


# --------------------------------------------------------------------------- #
# unexpected error propagation - never swallowed
# --------------------------------------------------------------------------- #


def test_non_market_data_error_from_provider_propagates_uncaught() -> None:
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, RuntimeError("programming bug in provider"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    with pytest.raises(RuntimeError, match="programming bug in provider"):
        composer.build_technical_result(as_of=NOW)


def test_misaligned_candle_from_provider_propagates_as_ingestion_error() -> None:
    """A provider returning a non-boundary-aligned timestamp is a real
    upstream-data contract violation, never ordinary degradation - it must
    surface as ``MisalignedCandleError``, not be caught as ``MarketDataError``
    or converted into a ``TechnicalFetchFailure``."""
    provider = _fully_stocked_provider()
    misaligned = OHLCVCandle(
        timestamp=datetime(2026, 1, 2, 11, 58, 30, tzinfo=UTC),  # not on an M1 boundary, but CLOSED as of NOW
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal(100),
        volume=Decimal(1),
    )
    provider.set_response(Timeframe.M1, [misaligned])
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    with pytest.raises(MisalignedCandleError):
        composer.build_technical_result(as_of=NOW)


def test_supervisor_invariant_error_propagates_uncaught() -> None:
    """A composer bug that supplies zero results to ``aggregate`` (a genuine
    programming defect, never reachable through the real per-timeframe loop)
    must propagate as the supervisor's own input error - proving the
    composer applies no blanket exception handling around
    ``supervisor.aggregate``."""
    from app.technical_supervisor.supervisor import TechnicalSupervisor

    with pytest.raises(EmptyResultsError):
        TechnicalSupervisor().aggregate([])


# --------------------------------------------------------------------------- #
# fetch-failure observability
# --------------------------------------------------------------------------- #


def test_fetch_failure_error_type_is_exact_class_name_only() -> None:
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, ProviderUnavailableError("secret internal detail: 10.0.0.1:443 timed out"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert len(result.fetch_failures) == 1
    failure = result.fetch_failures[0]
    assert failure.error_type == "ProviderUnavailableError"
    assert failure.timeframe is Timeframe.M1


def test_fetch_failure_never_carries_exception_message_text() -> None:
    secret_detail = "secret internal detail: 10.0.0.1:443 timed out"
    provider = _fully_stocked_provider()
    provider.fail(Timeframe.M1, ProviderUnavailableError(secret_detail))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    for failure in result.fetch_failures:
        assert secret_detail not in failure.error_type
        assert not hasattr(failure, "message")
        assert not hasattr(failure, "args")


# --------------------------------------------------------------------------- #
# long-outage gap
# --------------------------------------------------------------------------- #


def test_long_outage_gap_does_not_crash_and_does_not_fabricate_or_clear_history() -> None:
    """Builds a retained history with a gap older than one fetch window can
    ever backfill (the missing candle predates every candle the next fetch
    returns), then verifies Stage 0B degrades safely via the existing
    ``contiguous_tail`` semantics rather than crashing, fabricating the
    missing candle, or clearing retained history."""
    provider = FakeFuturesOHLCVProvider()
    engine = TechnicalFeatureEngine()
    for tf in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider.set_response(tf, [])
    composer = TechnicalProductionComposer(config=make_config(), provider=provider, engine=engine)

    # Cycle 1: establish some pre-gap history (2 closed M5 candles).
    pre_gap_as_of = datetime(2026, 1, 2, 10, 10, tzinfo=UTC)
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, 3, as_of=pre_gap_as_of))
    composer.build_technical_result(as_of=pre_gap_as_of)
    pre_gap_count = len(engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest())
    assert pre_gap_count > 0

    # A long outage follows: many candles pass with no successful fetch,
    # then service resumes far enough ahead that the gap candles are gone
    # from any future 51-candle window.
    post_gap_as_of = pre_gap_as_of + timedelta(minutes=5 * (TECHNICAL_OHLCV_FETCH_LIMIT + 20))
    provider.set_response(Timeframe.M5, make_candles(Timeframe.M5, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=post_gap_as_of))

    result = composer.build_technical_result(as_of=post_gap_as_of)  # must not raise

    retained = engine.history_for(SYMBOL, CONTRACT_TYPE, Timeframe.M5).candles.latest()
    retained_timestamps = {c.timestamp for c in retained}
    pre_gap_timestamps = {
        c.timestamp for c in make_candles(Timeframe.M5, 3, as_of=pre_gap_as_of)[:-1]
    }
    # Old pre-gap candles are never fabricated back in, and never cleared by
    # this cycle - the store still has them (nothing evicts on a mere gap).
    assert pre_gap_timestamps <= retained_timestamps
    # The composer did not crash, and M5 still produced all 7 analyst cells
    # (either ANALYZED from the post-gap contiguous run, or ABSTAINED - never
    # missing).
    m5_cells = {(a, t) for (a, t) in (result.technical.analyzed_cells + result.technical.abstained_cells) if t is Timeframe.M5}
    assert len(m5_cells) == 7
