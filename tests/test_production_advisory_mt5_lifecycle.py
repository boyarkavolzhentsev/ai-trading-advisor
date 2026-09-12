"""MT5 Price Authority Stage B lifecycle correction: ``ProductionAdvisoryComposer.
run_cycle`` - not ``run_runtime_cycle`` - now owns exactly one MT5
``initialize()``/``shutdown()`` pair per advisory cycle, opened BEFORE the
Technical MT5 OHLCV read (``MT5OHLCVProvider.get_ohlcv`` ->
``MT5Client.rates()``) and closed only after both that read and every
runtime MT5 read complete - because both now share the SAME MT5 connection,
and ``MT5Client.rates()`` requires the connection to already be initialized
(raising ``MT5NotInitializedError``, never a ``MarketDataError``, otherwise).

Proves the real call order using ``LifecycleTrackingMT5Client`` - a fake
that enforces the exact same lifecycle contract the real ``MT5Client``
does, never a lenient "always available" or "always UNAVAILABLE" stand-in
- so a regression that reintroduces the original defect (Technical reading
MT5 before initialize) would make these tests fail with
``MT5NotInitializedError``, not silently pass. No real MT5 terminal, no
real Binance network access, and no advisory-relevant business outcome
(Decision/Risk/Setup Construction) is asserted here - only lifecycle
ordering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.production_advisory.composer as composer_module
from app.core.enums.market import Timeframe
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.market_data.exceptions import MarketDataError
from app.market_data.providers.mt5.provider import MT5OHLCVProvider
from app.mt5.errors import MT5NotInitializedError
from app.production_advisory.composer import ProductionAdvisoryComposer
from tests.production_advisory_support import (
    AS_OF,
    FakeFlowBootstrap,
    FakeRecordPersistence,
    LifecycleTrackingMT5Client,
    all_trade_ids,
    build_config,
)


def _build_lifecycle_composer(
    tmp_path: Path, client: LifecycleTrackingMT5Client, **composer_overrides: object
) -> ProductionAdvisoryComposer:
    tracking_dir = tmp_path / "tracking"
    provenance_dir = tmp_path / "provenance"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    provenance_dir.mkdir(parents=True, exist_ok=True)
    config = build_config(
        rollover_state_path=tmp_path / "rollover.json",
        tracking_directory=tracking_dir,
        provenance_directory=provenance_dir,
    )
    fields: dict[str, object] = {
        "config": config,
        "flow_bootstrap": FakeFlowBootstrap(),
        "mt5_client": client,
        "tracking_persistence": FakeRecordPersistence(),
        "provenance_persistence": FakeRecordPersistence(),
    }
    fields.update(composer_overrides)
    return ProductionAdvisoryComposer(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# H. the fake itself models the real defect (test-gap closure)
# --------------------------------------------------------------------------- #


def test_lifecycle_fake_rates_before_initialize_raises_mt5_not_initialized_error() -> None:
    client = LifecycleTrackingMT5Client()
    with pytest.raises(MT5NotInitializedError):
        client.rates(symbol="BTCUSDt", timeframe=Timeframe.M1, count=1)


def test_mt5_not_initialized_error_is_not_a_market_data_error() -> None:
    """The exact hierarchy fact that made the original defect an uncaught
    crash rather than a graceful, Technical-catchable degradation:
    ``TechnicalProductionComposer.build_technical_result`` only catches
    ``MarketDataError`` (see ``app/technical/production.py``)."""
    assert not issubclass(MT5NotInitializedError, MarketDataError)


def test_uninitialized_client_makes_mt5_ohlcv_provider_raise_before_any_technical_catch() -> None:
    """The exact defect this correction fixes, reproduced directly against
    the real, unmodified ``MT5OHLCVProvider`` and the lifecycle-faithful
    fake: reading OHLCV before ``initialize()`` raises
    ``MT5NotInitializedError`` - a bug the OLD ``FakeMT5Client`` (which
    returned ``"UNAVAILABLE"`` unconditionally) could never have caught."""
    client = LifecycleTrackingMT5Client()
    provider = MT5OHLCVProvider(client=client, server_timezone="UTC")

    with pytest.raises(MT5NotInitializedError):
        provider.get_ohlcv("BTCUSDt", Timeframe.M1, limit=1)


# --------------------------------------------------------------------------- #
# A, B. real call order: initialize before rates, one shared client
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_initialize_occurs_before_first_technical_rates_call(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert "initialize" in client.call_log
    assert "rates" in client.call_log
    assert client.call_log.index("initialize") < client.call_log.index("rates")


@pytest.mark.asyncio
async def test_technical_rates_and_runtime_reads_use_the_same_client_instance(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    assert composer._technical_composer._provider._client is composer._mt5_client  # type: ignore[attr-defined]
    assert composer._mt5_client is client

    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    # rates() (Technical) and positions()/history_deals() (runtime) were all
    # observed on this ONE fake - never a second, independently-initialized
    # connection.
    assert "rates" in client.call_log
    assert "positions" in client.call_log
    assert "history_deals" in client.call_log


# --------------------------------------------------------------------------- #
# C, D, E. exactly one initialize, one shutdown, shutdown last
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_exactly_one_initialize_per_cycle(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert client.initialize_calls == 1


@pytest.mark.asyncio
async def test_exactly_one_shutdown_per_cycle(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert client.shutdown_calls == 1


@pytest.mark.asyncio
async def test_shutdown_occurs_after_technical_and_runtime_reads(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert client.call_log[-1] == "shutdown"
    shutdown_index = client.call_log.index("shutdown")
    assert shutdown_index > client.call_log.index("rates")
    assert shutdown_index > client.call_log.index("positions")
    assert shutdown_index > client.call_log.index("history_deals")


@pytest.mark.asyncio
async def test_two_consecutive_cycles_each_get_their_own_initialize_shutdown_pair(tmp_path: Path) -> None:
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids(prefix="T1"))
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids(prefix="T2"))

    assert client.initialize_calls == 2
    assert client.shutdown_calls == 2


# --------------------------------------------------------------------------- #
# F, G. shutdown guaranteed on failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_shutdown_still_happens_if_technical_raises(tmp_path: Path) -> None:
    class RaisingTechnicalComposer:
        def build_technical_result(self, *, as_of: object) -> object:
            raise RuntimeError("boom: technical bug, not a MarketDataError")

    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client, technical_composer=RaisingTechnicalComposer())
    await composer.startup()

    with pytest.raises(RuntimeError, match="boom"):
        await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert client.shutdown_calls == 1


@pytest.mark.asyncio
async def test_shutdown_still_happens_if_runtime_cycle_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_run_runtime_cycle(**kwargs: object) -> object:
        raise RuntimeError("boom: runtime cycle bug")

    monkeypatch.setattr(composer_module, "run_runtime_cycle", raising_run_runtime_cycle)
    client = LifecycleTrackingMT5Client()
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    with pytest.raises(RuntimeError, match="boom"):
        await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert client.shutdown_calls == 1


@pytest.mark.asyncio
async def test_technical_mt5_degraded_but_initialized_gracefully_discards_never_raises(tmp_path: Path) -> None:
    """``TERMINAL_UNAVAILABLE``/``ACCOUNT_UNAVAILABLE`` still leave the real
    ``MT5Client`` connection ``_initialized`` (only ``INITIALIZATION_FAILED``/
    ``LOGIN_FAILED`` do not - see ``app.mt5.client.MT5Client.initialize``):
    ``rates()`` is still attempted (never skipped) and degrades gracefully
    to ``"UNAVAILABLE"`` - a ``MarketDataError`` Technical's own per-timeframe
    catch already handles - never ``MT5NotInitializedError``, never a crash.
    """
    client = LifecycleTrackingMT5Client(
        runtime_status=MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.TERMINAL_UNAVAILABLE)
    )
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert "rates" in client.call_log
    assert len(result.technical_fetch_failures) > 0
    assert client.initialize_calls == 1
    assert client.shutdown_calls == 1


@pytest.mark.asyncio
async def test_technical_mt5_initialization_failed_discards_via_not_initialized_catch(tmp_path: Path) -> None:
    """``INITIALIZATION_FAILED`` (the raw ``mt5.initialize()`` call itself
    never succeeded) leaves the real ``MT5Client`` connection NOT
    ``_initialized`` - ``rates()`` would raise ``MT5NotInitializedError``.
    ``ProductionAdvisoryComposer.run_cycle`` must catch exactly that
    (never letting it propagate uncaught) and discard Technical for this
    cycle, exactly like any other full-cycle fetch failure - proving the
    original defect this correction fixes cannot recur."""
    client = LifecycleTrackingMT5Client(
        runtime_status=MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.INITIALIZATION_FAILED)
    )
    composer = _build_lifecycle_composer(tmp_path, client)
    await composer.startup()

    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert "rates" in client.call_log  # attempted - never pre-emptively skipped
    assert result.technical_fetch_failures == ()  # discarded via the exception catch, not a per-timeframe failure list
    assert result.runtime_cycle_result.outcome is RuntimeCycleOutcome.BLOCKED
    assert client.initialize_calls == 1
    assert client.shutdown_calls == 1
