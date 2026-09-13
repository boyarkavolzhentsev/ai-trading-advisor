"""FlowRealtimeBootstrap constructor dependency-wiring regression tests
(corrective review, "FLOW REALTIME BOOTSTRAP INJECTED-REST-CLIENT WIRING").

Proves the two previously-conflated constructor questions - "must a REST
client be self-constructed" vs "must a default REST-backed provider be
built for the two dependencies that actually consume it
(open_interest_provider/snapshot_fetcher)" - are now independent, using
only fake/in-process transports (zero real network for the bootstrap's
websocket side; a real, but never-started, ``BinanceRestClient`` for the
identity/construction-wiring assertions below, exactly mirroring the
existing ``test_stop_closes_only_owned_rest_client``/
``test_stop_closes_self_constructed_rest_client`` precedent in
``tests/test_flow_realtime_bootstrap.py``).

``tests.flow_realtime_bootstrap_support.OMITTED`` is used throughout to mean
"genuinely omit this dependency, let production derive it" - as distinct
from that helper's own default ("substitute a fake"), which every other
existing Flow bootstrap test continues to rely on unchanged.
"""

from __future__ import annotations

import pytest

from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures.provider import BinanceFuturesMarketDataProvider
from tests.flow_realtime_bootstrap_support import (
    OMITTED,
    FakeFundingIntervalCache,
    FakeOpenInterestSource,
    default_snapshot_fetcher,
    make_bootstrap,
)


# --------------------------------------------------------------------------- #
# A. No injected REST client, all derived dependencies omitted
# --------------------------------------------------------------------------- #


def test_no_rest_client_all_omitted_self_constructs_everything() -> None:
    bootstrap, _, _ = make_bootstrap(
        rest_client=None,
        open_interest_provider=OMITTED,
        snapshot_fetcher=OMITTED,
        funding_interval_cache=OMITTED,
    )
    try:
        assert bootstrap._rest_client is not None
        assert bootstrap._owns_rest_client is True
        assert bootstrap._open_interest_provider is not None
        assert isinstance(bootstrap._open_interest_provider, BinanceFuturesMarketDataProvider)
        assert bootstrap._snapshot_fetcher is not None
        assert bootstrap._funding_interval_cache is not None
    finally:
        bootstrap._rest_client.close()


# --------------------------------------------------------------------------- #
# B. Injected REST client, all derived dependencies omitted - THE PRIMARY BUG REGRESSION
# --------------------------------------------------------------------------- #


def test_injected_rest_client_all_omitted_derives_from_injected_client_no_second_client() -> None:
    injected = BinanceRestClient()
    try:
        bootstrap, _, _ = make_bootstrap(
            rest_client=injected,
            open_interest_provider=OMITTED,
            snapshot_fetcher=OMITTED,
            funding_interval_cache=OMITTED,
        )
        assert bootstrap._rest_client is injected  # no second REST client constructed
        assert bootstrap._owns_rest_client is False
        assert bootstrap._open_interest_provider is not None
        assert isinstance(bootstrap._open_interest_provider, BinanceFuturesMarketDataProvider)
        assert bootstrap._snapshot_fetcher is not None
        assert bootstrap._funding_interval_cache is not None
    finally:
        injected.close()


# --------------------------------------------------------------------------- #
# C. Injected REST client + explicit open_interest_provider only
# --------------------------------------------------------------------------- #


def test_injected_rest_client_explicit_open_interest_provider_preserved() -> None:
    injected = BinanceRestClient()
    explicit_oi = FakeOpenInterestSource()
    try:
        bootstrap, _, _ = make_bootstrap(
            rest_client=injected,
            open_interest_provider=explicit_oi,
            snapshot_fetcher=OMITTED,
            funding_interval_cache=OMITTED,
        )
        assert bootstrap._rest_client is injected
        assert bootstrap._open_interest_provider is explicit_oi  # preserved by identity
        assert bootstrap._snapshot_fetcher is not None  # still derived from the injected client
        assert bootstrap._funding_interval_cache is not None
    finally:
        injected.close()


# --------------------------------------------------------------------------- #
# D. Injected REST client + explicit snapshot_fetcher only
# --------------------------------------------------------------------------- #


def test_injected_rest_client_explicit_snapshot_fetcher_preserved() -> None:
    injected = BinanceRestClient()

    async def explicit_fetcher(symbol: str):  # pragma: no cover - identity only, never called
        raise AssertionError("never invoked in this construction-only test")

    try:
        bootstrap, _, _ = make_bootstrap(
            rest_client=injected,
            open_interest_provider=OMITTED,
            snapshot_fetcher=explicit_fetcher,
            funding_interval_cache=OMITTED,
        )
        assert bootstrap._rest_client is injected
        assert bootstrap._snapshot_fetcher is explicit_fetcher  # preserved by identity
        assert bootstrap._open_interest_provider is not None  # still derived from the injected client
        assert isinstance(bootstrap._open_interest_provider, BinanceFuturesMarketDataProvider)
        assert bootstrap._funding_interval_cache is not None
    finally:
        injected.close()


# --------------------------------------------------------------------------- #
# E. Injected REST client + all three explicit -> no default provider needed
# --------------------------------------------------------------------------- #


def test_injected_rest_client_all_explicit_no_default_provider_constructed() -> None:
    injected = BinanceRestClient()
    explicit_oi = FakeOpenInterestSource()
    explicit_funding = FakeFundingIntervalCache()

    async def explicit_fetcher(symbol: str):  # pragma: no cover - identity only, never called
        raise AssertionError("never invoked in this construction-only test")

    constructed_providers: list[BinanceFuturesMarketDataProvider] = []
    real_init = BinanceFuturesMarketDataProvider.__init__

    def _spy_init(self, *args, **kwargs):
        constructed_providers.append(self)
        real_init(self, *args, **kwargs)

    BinanceFuturesMarketDataProvider.__init__ = _spy_init  # type: ignore[method-assign]
    try:
        bootstrap, _, _ = make_bootstrap(
            rest_client=injected,
            open_interest_provider=explicit_oi,
            snapshot_fetcher=explicit_fetcher,
            funding_interval_cache=explicit_funding,
        )
        assert bootstrap._rest_client is injected
        assert bootstrap._open_interest_provider is explicit_oi
        assert bootstrap._snapshot_fetcher is explicit_fetcher
        assert bootstrap._funding_interval_cache is explicit_funding
        assert constructed_providers == []  # no default BinanceFuturesMarketDataProvider ever built
    finally:
        BinanceFuturesMarketDataProvider.__init__ = real_init  # type: ignore[method-assign]
        injected.close()


# --------------------------------------------------------------------------- #
# F. Cleanup ownership: injected REST client is never closed by stop()
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_injected_rest_client_never_closed_by_stop_when_all_omitted() -> None:
    close_calls = {"count": 0}

    class TrackedRestClient(BinanceRestClient):
        def close(self) -> None:
            close_calls["count"] += 1
            super().close()

    injected = TrackedRestClient()
    bootstrap, _, _ = make_bootstrap(
        rest_client=injected,
        open_interest_provider=OMITTED,
        snapshot_fetcher=OMITTED,
        funding_interval_cache=OMITTED,
    )

    await bootstrap.start()
    await bootstrap.stop()

    assert close_calls["count"] == 0  # never closed by the bootstrap itself
    injected.close()  # caller's own responsibility


# --------------------------------------------------------------------------- #
# Startup regression (section 7): the exact previously-failing construction,
# started for real (fake transports only - zero real network), proving the
# AttributeError on a None provider is no longer reachable.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_startup_with_injected_rest_client_and_omitted_providers_does_not_raise() -> None:
    """Before the fix, this exact construction (mirroring
    ``ProductionAdvisoryComposer._default_flow_bootstrap``'s own real
    wiring) would fail at ``start()`` with either
    ``AttributeError: 'NoneType' object has no attribute
    'get_order_book_snapshot'`` (order-book resync) or an
    ``open_interest_poller`` task failure - both stemming from
    ``default_provider`` staying ``None``. No real network is used: only
    the REST client object itself is real (never actually connected to;
    the bootstrap's websocket transports are fakes, per ``make_bootstrap``'s
    own convention), and its actual HTTP methods are never reached within
    the bounded startup window this test uses.
    """
    injected = BinanceRestClient()
    bootstrap, _, _ = make_bootstrap(
        rest_client=injected,
        open_interest_provider=OMITTED,
        snapshot_fetcher=OMITTED,
        funding_interval_cache=OMITTED,
    )
    try:
        await bootstrap.start()  # must not raise FlowRealtimeBootstrapStartupError
    finally:
        await bootstrap.stop()
        injected.close()


def test_default_snapshot_fetcher_and_fake_open_interest_source_still_importable() -> None:
    """Sanity: the existing fakes this module's own default ("use the fake")
    path relies on are unchanged by the OMITTED sentinel's introduction."""
    assert default_snapshot_fetcher is not None
    assert FakeOpenInterestSource is not None
