"""MT5 Price Authority Stage B production bootstrap wiring
(``app.production_advisory.composer``): using fakes/mocks only, proves
Flow stays wired to the Binance Futures provider with ``binance_symbol``
while Technical is now wired to ``MT5OHLCVProvider`` with ``mt5_symbol``,
``MT5_V1_TECHNICAL_TIMEFRAMES``, and the already-authoritative
``MT5RolloverPolicyConfig.rollover_timezone`` value - no new MT5 timezone
environment variable is introduced anywhere. No real Binance network
access, no real MT5 terminal, and no advisory cycle is ever run here.
"""

from __future__ import annotations

import ast
import inspect

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.mt5 import MT5_V1_TECHNICAL_TIMEFRAMES, MT5OHLCVProvider
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.config import SymbolMapping
from tests.production_advisory_support import FakeMT5Client, build_config

_MAPPING = SymbolMapping(logical_symbol="BTC", binance_symbol="BTCUSDT", mt5_symbol="BTCUSDt")


def _make_default_wired_composer(**config_overrides: object) -> ProductionAdvisoryComposer:
    """No ``flow_bootstrap``/``technical_composer`` override: exercises the
    real default wiring functions this stage changed."""
    config = build_config(symbol_mapping=_MAPPING, **config_overrides)
    composer = ProductionAdvisoryComposer(config=config, mt5_client=FakeMT5Client())
    composer._rest_client.close()  # never opened a real socket; closes the httpx.Client cleanly
    return composer


# --------------------------------------------------------------------------- #
# Flow: still Binance, still binance_symbol
# --------------------------------------------------------------------------- #


def test_flow_uses_the_shared_binance_rest_client() -> None:
    composer = _make_default_wired_composer()
    assert isinstance(composer._flow_bootstrap._rest_client, BinanceRestClient)  # type: ignore[attr-defined]


def test_flow_receives_binance_symbol_not_mt5_symbol() -> None:
    composer = _make_default_wired_composer()
    assert composer._flow_bootstrap._config.symbol == "BTCUSDT"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Technical: now MT5, now mt5_symbol
# --------------------------------------------------------------------------- #


def test_technical_uses_mt5_ohlcv_provider() -> None:
    composer = _make_default_wired_composer()
    assert isinstance(composer._technical_composer._provider, MT5OHLCVProvider)  # type: ignore[attr-defined]


def test_technical_receives_mt5_symbol_not_binance_symbol() -> None:
    composer = _make_default_wired_composer()
    assert composer._technical_composer._config.symbol == "BTCUSDt"  # type: ignore[attr-defined]


def test_technical_receives_the_mt5_v1_timeframe_preset() -> None:
    composer = _make_default_wired_composer()
    assert composer._technical_composer._timeframes == MT5_V1_TECHNICAL_TIMEFRAMES  # type: ignore[attr-defined]


def test_mt5_v1_timeframe_preset_excludes_d1_in_production_wiring() -> None:
    from app.core.enums.market import Timeframe

    composer = _make_default_wired_composer()
    assert Timeframe.D1 not in composer._technical_composer._timeframes  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# timezone reuse: rollover_timezone, no new env var
# --------------------------------------------------------------------------- #


def test_technical_provider_server_timezone_matches_rollover_policy() -> None:
    composer = _make_default_wired_composer(rollover_policy=MT5RolloverPolicyConfig(rollover_timezone="America/New_York"))
    assert composer._technical_composer._provider._server_timezone == "America/New_York"  # type: ignore[attr-defined]


def test_default_rollover_timezone_reused_verbatim_when_utc() -> None:
    composer = _make_default_wired_composer(rollover_policy=MT5RolloverPolicyConfig(rollover_timezone="UTC"))
    assert composer._technical_composer._provider._server_timezone == "UTC"  # type: ignore[attr-defined]


def test_bootstrap_wiring_introduces_no_new_mt5_timezone_env_var() -> None:
    """The only environment-variable names anywhere in production bootstrap
    whose name contains ``TIMEZONE`` are ``MT5_ROLLOVER_TIMEZONE`` (reused
    verbatim by the Technical ``MT5OHLCVProvider`` - see the wiring tests
    above) and the unrelated, pre-existing ``CALENDAR_SERVER_TIMEZONE`` - no
    second, independently-read MT5 timezone variable (e.g. an
    ``MT5_SERVER_TIMEZONE``/``MT5_OHLCV_TIMEZONE``) was introduced for
    Stage B."""
    import app.bootstrap.production as bootstrap_module

    tree = ast.parse(inspect.getsource(bootstrap_module))
    env_var_names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isupper() and "_" in node.value
    }
    timezone_shaped = {name for name in env_var_names if "TIMEZONE" in name}
    assert timezone_shaped == {"MT5_ROLLOVER_TIMEZONE", "CALENDAR_SERVER_TIMEZONE"}


# --------------------------------------------------------------------------- #
# resource sharing: one MT5 connection, one Binance REST client
# --------------------------------------------------------------------------- #


def test_technical_and_runtime_cycle_share_exactly_one_mt5_client() -> None:
    composer = _make_default_wired_composer()
    assert composer._technical_composer._provider._client is composer._mt5_client  # type: ignore[attr-defined]


def test_flow_and_composer_share_exactly_one_binance_rest_client() -> None:
    composer = _make_default_wired_composer()
    assert composer._flow_bootstrap._rest_client is composer._rest_client  # type: ignore[attr-defined]
