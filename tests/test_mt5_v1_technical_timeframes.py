"""MT5 Price Authority Stage B: the MT5 V1 Technical timeframe preset
(``app.market_data.providers.mt5.provider.MT5_V1_TECHNICAL_TIMEFRAMES``)
excludes ``Timeframe.D1`` (D1 is not enabled in MT5 V1), while the existing
Binance-native default preset
(``app.technical.timeframes.DEFAULT_TECHNICAL_TIMEFRAMES``) is left
completely untouched by this stage."""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.market_data.providers.mt5 import MT5_V1_TECHNICAL_TIMEFRAMES
from app.market_data.providers.mt5.provider import MT5_V1_TECHNICAL_TIMEFRAMES as _PROVIDER_MODULE_EXPORT
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES


def test_mt5_v1_technical_timeframes_is_exactly_m1_m5_m15_h1_h4() -> None:
    assert MT5_V1_TECHNICAL_TIMEFRAMES == (
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
    )


def test_mt5_v1_technical_timeframes_excludes_d1() -> None:
    assert Timeframe.D1 not in MT5_V1_TECHNICAL_TIMEFRAMES


def test_mt5_v1_technical_timeframes_re_exported_identically_from_package_root() -> None:
    assert MT5_V1_TECHNICAL_TIMEFRAMES is _PROVIDER_MODULE_EXPORT


def test_default_technical_timeframes_unchanged_by_stage_b() -> None:
    assert DEFAULT_TECHNICAL_TIMEFRAMES == (
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
        Timeframe.D1,
    )


def test_default_technical_timeframes_still_includes_d1() -> None:
    """The Binance-native default contour is untouched: only the MT5-specific
    preset excludes D1, never the shared default."""
    assert Timeframe.D1 in DEFAULT_TECHNICAL_TIMEFRAMES


def test_mt5_v1_technical_timeframes_is_a_strict_subset_of_the_default_preset() -> None:
    assert set(MT5_V1_TECHNICAL_TIMEFRAMES) < set(DEFAULT_TECHNICAL_TIMEFRAMES)
