"""MT5 Price Authority Stage B ``TechnicalProductionComposer`` provider
contract: the composer depends only on ``app.market_data.protocols.
OHLCVProvider``, propagates the exact ``build_technical_result(as_of=...)``
value to every ``provider.get_ohlcv`` call, works unchanged against both a
Binance-shaped fake and the real ``MT5OHLCVProvider``, and fails fast when
``Timeframe.M15`` is missing from an injected ``timeframes`` set.

Provider-agnosticism itself (no ``app.market_data.providers.mt5`` import, no
textual ``MT5OHLCVProvider`` mention, no ``isinstance`` branching anywhere
under ``app/technical``) is already proven exhaustively by
``tests/test_technical_no_mt5_provider_coupling.py`` - not re-proven here.
No real network access and no real MT5 terminal happens anywhere in this
file.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums.market import Timeframe
from app.core.models.mt5_rate import MT5RawRate
from app.market_data.providers.mt5.provider import MT5_V1_TECHNICAL_TIMEFRAMES, MT5OHLCVProvider
from app.technical.production import TECHNICAL_OHLCV_FETCH_LIMIT, TechnicalProductionComposer
from tests.technical_production_support import (
    CONTRACT_TYPE,
    NOW,
    SYMBOL,
    FakeFuturesOHLCVProvider,
    make_candles,
    make_config,
)

_SERVER_TIMEZONE = "UTC"  # no DST in UTC: raw epoch equals the intended UTC instant directly


def _fully_stocked_binance_shaped_provider() -> FakeFuturesOHLCVProvider:
    provider = FakeFuturesOHLCVProvider()
    for timeframe in MT5_V1_TECHNICAL_TIMEFRAMES:
        provider.set_response(timeframe, make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW))
    return provider


class _FakeMT5RatesClient:
    """Stands in for ``MT5Client.rates()`` only, generating deterministic,
    contiguous, UTC-aligned bars for whatever ``(timeframe, count)`` is
    requested - including the internal ``count=208`` H1 read
    ``MT5OHLCVProvider`` issues for H4 synthesis, independent of any earlier
    H1 call. No live terminal, no ``MetaTrader5`` import."""

    def __init__(self, *, as_of: datetime) -> None:
        self._as_of = as_of

    def rates(self, *, symbol: str, timeframe: Timeframe, count: int) -> tuple[str, tuple[MT5RawRate, ...]]:
        candles = make_candles(timeframe, count, as_of=self._as_of)
        raws = tuple(
            MT5RawRate(
                epoch_seconds=int(candle.timestamp.timestamp()),
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                tick_volume=int(candle.volume),
                real_volume=0,
            )
            for candle in candles
        )
        return "OK", raws


# --------------------------------------------------------------------------- #
# provider-agnostic acceptance
# --------------------------------------------------------------------------- #


def test_composer_accepts_a_binance_shaped_ohlcv_provider() -> None:
    provider = _fully_stocked_binance_shaped_provider()
    composer = TechnicalProductionComposer(
        config=make_config(), provider=provider, timeframes=MT5_V1_TECHNICAL_TIMEFRAMES
    )

    result = composer.build_technical_result(as_of=NOW)

    assert result.fetch_failures == ()
    assert result.m15_market_structure is not None


def test_composer_works_against_the_real_mt5_ohlcv_provider() -> None:
    """End-to-end against the real, unmodified ``MT5OHLCVProvider`` (M1/M5/
    M15/H1 direct, H4 synthesized from 208 raw H1 bars) - only its
    underlying ``MT5Client.rates()`` call is faked."""
    client = _FakeMT5RatesClient(as_of=NOW)
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    composer = TechnicalProductionComposer(
        config=make_config(), provider=provider, timeframes=MT5_V1_TECHNICAL_TIMEFRAMES
    )

    result = composer.build_technical_result(as_of=NOW)

    assert result.fetch_failures == ()
    assert result.m15_market_structure is not None
    assert set(result.technical.expected_timeframes) == set(MT5_V1_TECHNICAL_TIMEFRAMES)
    assert Timeframe.D1 not in result.technical.expected_timeframes


# --------------------------------------------------------------------------- #
# as_of propagation
# --------------------------------------------------------------------------- #


def test_every_get_ohlcv_call_receives_the_exact_build_technical_result_as_of() -> None:
    provider = _fully_stocked_binance_shaped_provider()
    composer = TechnicalProductionComposer(
        config=make_config(), provider=provider, timeframes=MT5_V1_TECHNICAL_TIMEFRAMES
    )

    composer.build_technical_result(as_of=NOW)

    assert len(provider.calls) == len(MT5_V1_TECHNICAL_TIMEFRAMES)
    for _symbol, _timeframe, _limit, as_of in provider.calls:
        assert as_of == NOW
        assert as_of is NOW  # the exact object passed through, never a copy/derivation


def test_a_different_as_of_on_a_later_cycle_is_propagated_unchanged() -> None:
    from datetime import timedelta

    provider = _fully_stocked_binance_shaped_provider()
    composer = TechnicalProductionComposer(
        config=make_config(), provider=provider, timeframes=MT5_V1_TECHNICAL_TIMEFRAMES
    )
    composer.build_technical_result(as_of=NOW)

    later_as_of = NOW + timedelta(minutes=1)
    for timeframe in MT5_V1_TECHNICAL_TIMEFRAMES:
        provider.set_response(timeframe, make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=later_as_of))
    composer.build_technical_result(as_of=later_as_of)

    second_cycle_as_ofs = [call[3] for call in provider.calls[len(MT5_V1_TECHNICAL_TIMEFRAMES) :]]
    assert all(as_of == later_as_of for as_of in second_cycle_as_ofs)


# --------------------------------------------------------------------------- #
# M15 fail-fast invariant
# --------------------------------------------------------------------------- #


def test_missing_m15_in_injected_timeframes_raises_before_any_fetch() -> None:
    provider = FakeFuturesOHLCVProvider()
    with pytest.raises(ValueError, match="Timeframe.M15"):
        TechnicalProductionComposer(
            config=make_config(),
            provider=provider,
            timeframes=(Timeframe.M1, Timeframe.H1, Timeframe.H4),
        )
    assert provider.calls == []


def test_default_timeframes_and_mt5_v1_timeframes_both_satisfy_the_m15_invariant() -> None:
    from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES

    provider_default = _fully_stocked_binance_shaped_provider()
    for timeframe in DEFAULT_TECHNICAL_TIMEFRAMES:
        provider_default.set_response(timeframe, make_candles(timeframe, TECHNICAL_OHLCV_FETCH_LIMIT, as_of=NOW))
    TechnicalProductionComposer(config=make_config(), provider=provider_default)  # default timeframes

    provider_mt5 = _fully_stocked_binance_shaped_provider()
    TechnicalProductionComposer(
        config=make_config(), provider=provider_mt5, timeframes=MT5_V1_TECHNICAL_TIMEFRAMES
    )
