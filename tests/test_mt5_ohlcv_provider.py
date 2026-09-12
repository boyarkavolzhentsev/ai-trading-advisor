"""``MT5OHLCVProvider`` (``app.market_data.providers.mt5.provider``) - a fake
MT5-rates client only; no live terminal, no ``MetaTrader5`` import."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.market import Timeframe
from app.core.models.mt5_rate import MT5RawRate
from app.market_data.exceptions import (
    InvalidProviderResponseError,
    ProviderUnavailableError,
    UnsupportedTimeframeError,
)
from app.market_data.providers.mt5.provider import H4_RAW_H1_LOOKBACK, MT5OHLCVProvider

_SYMBOL = "BTCUSDt"
_SERVER_TIMEZONE = "UTC"  # no DST in UTC: raw epoch equals the intended UTC instant directly


class _FakeRatesClient:
    """Stands in for ``MT5Client.rates()`` only - no other ``MT5Client``
    method exists on this fake, and no live terminal is ever touched."""

    def __init__(self, *, responses: dict[Timeframe, tuple[str, tuple[MT5RawRate, ...]]]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, Timeframe, int]] = []

    def rates(self, *, symbol: str, timeframe: Timeframe, count: int) -> tuple[str, tuple[MT5RawRate, ...]]:
        self.calls.append((symbol, timeframe, count))
        return self._responses.get(timeframe, ("OK", ()))


def _raw_rate_at(dt: datetime, **overrides: Decimal | int) -> MT5RawRate:
    fields: dict[str, object] = {
        "epoch_seconds": int(dt.timestamp()),
        "open": Decimal("100"),
        "high": Decimal("101"),
        "low": Decimal("99"),
        "close": Decimal("100.5"),
        "tick_volume": 500,
        "real_volume": 0,
    }
    fields.update(overrides)
    return MT5RawRate(**fields)


def _h1_series(*, count: int, last_start: datetime) -> tuple[MT5RawRate, ...]:
    """``count`` contiguous, ascending, hourly raw H1 rates, the last one
    timestamped exactly at ``last_start`` (the still-forming bar)."""
    return tuple(_raw_rate_at(last_start - timedelta(hours=count - 1 - i)) for i in range(count))


# --- direct timeframes ---


@pytest.mark.parametrize("timeframe", [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1])
def test_direct_timeframes_map_raw_rates_unchanged(timeframe: Timeframe) -> None:
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    client = _FakeRatesClient(responses={timeframe: ("OK", (_raw_rate_at(dt),))})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    candles = provider.get_ohlcv(_SYMBOL, timeframe, limit=1)

    assert len(candles) == 1
    assert candles[0].timestamp == dt
    assert client.calls == [(_SYMBOL, timeframe, 1)]


@pytest.mark.parametrize("timeframe", [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1])
def test_direct_timeframes_accept_as_of_without_error_or_effect(timeframe: Timeframe) -> None:
    """MT5 Price Authority Stage A contract correction: ``OHLCVProvider``'s
    ``as_of`` keyword must be accepted (never a ``TypeError``) even where
    the provider has no use for it - direct timeframes do no closed/forming
    filtering here at all."""
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    client = _FakeRatesClient(responses={timeframe: ("OK", (_raw_rate_at(dt),))})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    with_as_of = provider.get_ohlcv(_SYMBOL, timeframe, limit=1, as_of=dt)
    without_as_of = provider.get_ohlcv(_SYMBOL, timeframe, limit=1)

    assert with_as_of == without_as_of


def test_direct_timeframe_unavailable_raises() -> None:
    client = _FakeRatesClient(responses={Timeframe.H1: ("UNAVAILABLE", ())})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    with pytest.raises(ProviderUnavailableError):
        provider.get_ohlcv(_SYMBOL, Timeframe.H1, limit=51)


def test_direct_timeframe_empty_rates_returns_empty_list_not_fabricated() -> None:
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", ())})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    assert provider.get_ohlcv(_SYMBOL, Timeframe.H1, limit=51) == []


def test_direct_timeframe_malformed_bar_raises() -> None:
    bad_raw = _raw_rate_at(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC), open=Decimal("0"))
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", (bad_raw,))})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    with pytest.raises(InvalidProviderResponseError):
        provider.get_ohlcv(_SYMBOL, Timeframe.H1, limit=1)


def test_direct_timeframe_timestamp_normalization_failure_raises() -> None:
    gap_local = datetime(2026, 3, 29, 3, 30, 0)  # Europe/Bucharest spring-forward gap
    raw_epoch = int(gap_local.replace(tzinfo=UTC).timestamp())
    bad_raw = MT5RawRate(
        epoch_seconds=raw_epoch, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"),
        tick_volume=500, real_volume=0,
    )
    client = _FakeRatesClient(responses={Timeframe.M15: ("OK", (bad_raw,))})
    provider = MT5OHLCVProvider(client=client, server_timezone="Europe/Bucharest")
    with pytest.raises(InvalidProviderResponseError):
        provider.get_ohlcv(_SYMBOL, Timeframe.M15, limit=1)


# --- H4 ---


def test_h4_requests_exactly_208_raw_h1_bars() -> None:
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    forming_h1_start = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=forming_h1_start)
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)

    assert client.calls == [(_SYMBOL, Timeframe.H1, H4_RAW_H1_LOOKBACK)]


def test_h4_excludes_forming_h1_from_synthesis() -> None:
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    forming_h1_start = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)  # closes at 13:00, strictly after as_of
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=forming_h1_start)
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    result = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)

    assert result  # enough closed history to synthesize at least one H4 candle
    for candle in result:
        assert candle.timestamp + timedelta(hours=4) <= as_of  # fully closed by as_of - never the forming bucket
        assert candle.timestamp.minute == 0 and candle.timestamp.second == 0
        assert candle.timestamp.hour % 4 == 0


def test_h4_produces_at_least_50_closed_candles_from_208_raw_h1() -> None:
    """Proves the 208 lookback constant actually delivers the real V1
    warmup target even in the worst-case edge alignment used here."""
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    forming_h1_start = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=forming_h1_start)
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    result = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)

    assert len(result) >= 50


def test_h4_respects_requested_limit() -> None:
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    forming_h1_start = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=forming_h1_start)
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    result = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=3, as_of=as_of)

    assert len(result) == 3


def test_h4_unavailable_raises() -> None:
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    client = _FakeRatesClient(responses={Timeframe.H1: ("UNAVAILABLE", ())})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    with pytest.raises(ProviderUnavailableError):
        provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)


def test_h4_without_as_of_raises_value_error() -> None:
    """The core corrective-review invariant at the API-contract level: H4
    synthesis can never silently fall back to an independently sampled wall
    clock - the caller must supply the authoritative cycle ``as_of``."""
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC))
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    with pytest.raises(ValueError, match="as_of"):
        provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51)

    assert client.calls == []  # fails before ever attempting a raw MT5 read


# --- as_of determinism (Stage A corrective review) ---


def test_h4_closure_boundary_is_governed_by_as_of_not_wall_clock() -> None:
    """Mirrors the reviewed boundary example (H1 candle closing right around
    the cycle as_of): the H1 bar at 11:00 (closes at 12:00:00.000) is the
    4th/last member of the 08:00 H4 bucket. An as_of strictly before its
    close must exclude it (08:00 bucket incomplete -> no candle); an as_of
    at/after its close must include it (08:00 bucket complete -> candle
    produced) - entirely determined by the caller-supplied as_of, with zero
    dependence on the actual wall clock at test-run time."""
    boundary_h1_start = datetime(2026, 1, 10, 11, 0, 0, tzinfo=UTC)  # closes at 12:00:00.000
    target_bucket = datetime(2026, 1, 10, 8, 0, 0, tzinfo=UTC)
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=boundary_h1_start)
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    as_of_before_close = datetime(2026, 1, 10, 11, 59, 59, 900000, tzinfo=UTC)
    as_of_at_or_after_close = datetime(2026, 1, 10, 12, 0, 0, 50000, tzinfo=UTC)

    result_before = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of_before_close)
    result_after = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of_at_or_after_close)

    assert target_bucket not in [candle.timestamp for candle in result_before]
    assert target_bucket in [candle.timestamp for candle in result_after]


def test_h4_repeated_calls_with_identical_input_and_as_of_produce_identical_output() -> None:
    as_of = datetime(2026, 1, 10, 12, 30, 0, tzinfo=UTC)
    raws = _h1_series(count=H4_RAW_H1_LOOKBACK, last_start=datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC))
    client = _FakeRatesClient(responses={Timeframe.H1: ("OK", raws)})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)

    first = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)
    second = provider.get_ohlcv(_SYMBOL, Timeframe.H4, limit=51, as_of=as_of)

    assert first == second


# --- D1 ---


def test_d1_is_deterministically_unsupported() -> None:
    client = _FakeRatesClient(responses={})
    provider = MT5OHLCVProvider(client=client, server_timezone=_SERVER_TIMEZONE)
    with pytest.raises(UnsupportedTimeframeError):
        provider.get_ohlcv(_SYMBOL, Timeframe.D1, limit=51)
    assert client.calls == []  # never even attempts a raw MT5 read for D1
