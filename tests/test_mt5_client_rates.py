"""Stage 10A ``MT5Client.rates()`` adapter behavior - raw MT5 row ->
``MT5RawRate`` normalization (no timestamp/UTC conversion - that is
``app.market_data.providers.mt5.timezone``'s job, one layer above), typed
OK/UNAVAILABLE read status, no raw MT5 object leakage."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.market import Timeframe
from app.core.models.mt5_rate import MT5RawRate
from app.mt5.client import MT5Client
from app.mt5.errors import MT5NotInitializedError
from tests.mt5_support import FakeRawMT5Module, default_raw_rate, default_terminal_info


def test_rates_maps_raw_row_to_mt5_raw_rate() -> None:
    raw = FakeRawMT5Module(
        rates_result=(
            default_raw_rate(time=1_800_000_000, open=100.25, high=101.75, low=99.1, close=100.6, tick_volume=777, real_volume=123),
        )
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()

    status, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=1)

    assert status == "OK"
    assert isinstance(rates[0], MT5RawRate)
    assert rates[0].epoch_seconds == 1_800_000_000
    assert rates[0].open == Decimal("100.25")
    assert rates[0].high == Decimal("101.75")
    assert rates[0].low == Decimal("99.1")
    assert rates[0].close == Decimal("100.6")
    assert rates[0].tick_volume == 777
    assert rates[0].real_volume == 123


def test_rates_decimal_normalization_avoids_float_repr_artifacts() -> None:
    raw = FakeRawMT5Module(rates_result=(default_raw_rate(time=1_800_000_000, open=0.1, high=0.3, low=0.05, close=0.2),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.M1, count=1)
    assert rates[0].open == Decimal("0.1")
    assert rates[0].high == Decimal("0.3")


def test_rates_no_bars_is_ok_empty() -> None:
    raw = FakeRawMT5Module(rates_result=())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=10)
    assert status == "OK"
    assert rates == ()


def test_rates_none_result_is_unavailable() -> None:
    raw = FakeRawMT5Module(rates_result=None)
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=10)
    assert status == "UNAVAILABLE"
    assert rates == ()


def test_rates_unavailable_when_terminal_disconnected() -> None:
    raw = FakeRawMT5Module(terminal_info=default_terminal_info(connected=False))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=10)
    assert status == "UNAVAILABLE"
    assert rates == ()


def test_rates_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=10)


def test_rates_after_shutdown_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    with pytest.raises(MT5NotInitializedError):
        client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=10)


def test_rates_unsupported_timeframe_raises_value_error() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    with pytest.raises(ValueError):
        client.rates(symbol="BTCUSDt", timeframe=Timeframe.D1, count=10)


def test_rates_passes_symbol_count_and_correct_mt5_timeframe_constant_through() -> None:
    raw = FakeRawMT5Module(rates_result=())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=42)
    assert raw.copy_rates_from_pos_calls == [("BTCUSDt", raw.TIMEFRAME_H1, 0, 42)]


def test_rates_raw_object_never_returned() -> None:
    raw = FakeRawMT5Module(rates_result=(default_raw_rate(time=1_800_000_000),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, rates = client.rates(symbol="BTCUSDt", timeframe=Timeframe.H1, count=1)
    assert all(isinstance(rate, MT5RawRate) for rate in rates)
