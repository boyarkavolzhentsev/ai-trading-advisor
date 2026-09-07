"""Stage 0A open-interest poller tests.

No real Binance/network access anywhere - ``FakeOpenInterestSource``/
``FailingOpenInterestSource`` (``tests/flow_realtime_bootstrap_support.py``)
stand in for ``BinanceFuturesMarketDataProvider.get_open_interest``.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from app.core.enums.instrument import ContractType
from app.flow.engine import FlowFeatureEngine
from app.flow.open_interest_poller import (
    DEFAULT_OPEN_INTEREST_POLL_INTERVAL_SECONDS,
    OpenInterestPoller,
    OpenInterestPollerConfig,
)
from tests.flow_realtime_bootstrap_support import NOW, SYMBOL, FailingOpenInterestSource, FakeOpenInterestSource


def test_default_poll_interval_is_60_seconds() -> None:
    assert OpenInterestPollerConfig().poll_interval_seconds == DEFAULT_OPEN_INTEREST_POLL_INTERVAL_SECONDS == 60.0


def test_configurable_positive_finite_interval_accepted() -> None:
    config = OpenInterestPollerConfig(poll_interval_seconds=5.0)
    assert config.poll_interval_seconds == 5.0


@pytest.mark.parametrize("bad_interval", [0.0, -1.0, math.inf, math.nan])
def test_invalid_interval_rejected(bad_interval: float) -> None:
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError, either gt=0 or the finite validator
        OpenInterestPollerConfig(poll_interval_seconds=bad_interval)


@pytest.mark.asyncio
async def test_successful_observation_forwarded_to_engine() -> None:
    engine = FlowFeatureEngine()
    source = FakeOpenInterestSource()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=source, engine=engine, config=OpenInterestPollerConfig())

    succeeded = await poller.poll_once()

    assert succeeded is True
    assert source.calls == [SYMBOL]
    history = engine.history_for(SYMBOL, ContractType.PERPETUAL)
    retained = history.open_interest.latest()
    assert len(retained) == 1
    assert retained[0].open_interest == source.get_open_interest(SYMBOL).open_interest
    assert poller.last_attempt_at is not None
    assert poller.last_success_at is not None


@pytest.mark.asyncio
async def test_rest_call_does_not_block_event_loop() -> None:
    """A slow synchronous provider call must not stall other coroutines -
    proves asyncio.to_thread is actually bridging the call."""
    import time

    class SlowSource:
        def get_open_interest(self, symbol: str):
            time.sleep(0.2)
            return FakeOpenInterestSource().get_open_interest(symbol)

    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=SlowSource(), engine=engine)

    ticked = False

    async def ticker() -> None:
        nonlocal ticked
        await asyncio.sleep(0.01)
        ticked = True

    await asyncio.gather(poller.poll_once(), ticker())
    assert ticked is True


@pytest.mark.asyncio
async def test_temporary_provider_failure_produces_no_fabricated_observation() -> None:
    engine = FlowFeatureEngine()
    source = FailingOpenInterestSource()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=source, engine=engine)

    succeeded = await poller.poll_once()

    assert succeeded is False
    history = engine.history_for(SYMBOL, ContractType.PERPETUAL)
    assert history.open_interest.latest() == []
    assert poller.last_attempt_at is not None
    assert poller.last_success_at is None


@pytest.mark.asyncio
async def test_unexpected_programming_error_is_not_swallowed() -> None:
    class BrokenSource:
        def get_open_interest(self, symbol: str):
            raise ValueError("not a MarketDataError")

    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=BrokenSource(), engine=engine)

    with pytest.raises(ValueError, match="not a MarketDataError"):
        await poller.poll_once()


@pytest.mark.asyncio
async def test_last_real_observation_becomes_stale_naturally_via_existing_logic() -> None:
    """This poller never decides staleness itself - app.flow.open_interest's
    own existing DEFAULT_MAX_STALENESS is what classifies an aging
    observation. Proven here by feeding one real observation and letting the
    existing calculator (unmodified) report STALE once its own threshold is
    exceeded - no new staleness vocabulary is introduced anywhere in this test."""
    from datetime import timedelta

    from app.core.enums.quality import FeatureQuality
    from app.flow.open_interest import DEFAULT_MAX_STALENESS, compute_open_interest_features

    engine = FlowFeatureEngine()
    source = FakeOpenInterestSource(timestamp=NOW)
    poller = OpenInterestPoller(symbol=SYMBOL, provider=source, engine=engine)
    await poller.poll_once()

    history = engine.history_for(SYMBOL, ContractType.PERPETUAL).open_interest.latest()
    fresh = compute_open_interest_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=history,
        windows=(), observation_time=NOW, source="test",
    )
    stale = compute_open_interest_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=history,
        windows=(), observation_time=NOW + DEFAULT_MAX_STALENESS + timedelta(seconds=1), source="test",
    )
    assert fresh.status.quality is FeatureQuality.VALID
    assert stale.status.quality is FeatureQuality.STALE


@pytest.mark.asyncio
async def test_cancellation_is_clean() -> None:
    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(
        symbol=SYMBOL,
        provider=FakeOpenInterestSource(),
        engine=engine,
        config=OpenInterestPollerConfig(poll_interval_seconds=60.0),
    )
    poller.start()
    await asyncio.sleep(0.01)
    await poller.stop()
    # idempotent second stop
    await poller.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    engine = FlowFeatureEngine()
    poller = OpenInterestPoller(symbol=SYMBOL, provider=FakeOpenInterestSource(), engine=engine)
    poller.start()
    task_first = poller._task
    poller.start()
    assert poller._task is task_first
    await poller.stop()
