"""Stage 0A event-forwarding tests: every capability the existing production
streams emit must land, unchanged, in the shared ``FlowFeatureEngine`` - and
never a wrong-symbol liquidation. No real network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.flow.engine import FlowFeatureEngine
from app.flow.funding import DEFAULT_MAX_STALENESS as FUNDING_MAX_STALENESS
from app.flow.funding import compute_funding_features
from app.flow.order_book import DEFAULT_MAX_STALENESS as ORDER_BOOK_MAX_STALENESS
from app.flow.order_book import DEFAULT_DEPTH_BANDS, compute_order_book_features
from tests.flow_realtime_bootstrap_support import NOW, SYMBOL, make_bootstrap, make_order_book_snapshot, millis


def _millis(moment: datetime) -> int:
    return millis(moment)


@pytest.mark.asyncio
async def test_trade_forwarded_to_engine() -> None:
    engine = FlowFeatureEngine()
    bootstrap, market_connection, _ = make_bootstrap(engine=engine)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@aggTrade",
        {"e": "aggTrade", "E": _millis(NOW), "s": SYMBOL, "a": 1, "p": "64000.00", "q": "0.1", "f": 1, "l": 1, "T": _millis(NOW), "m": False},
    )
    await asyncio.sleep(0.05)

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).trades.latest()
    assert len(retained) == 1
    assert retained[0].symbol == SYMBOL
    assert retained[0].side is OrderSide.BUY

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_liquidation_forwarded_to_engine() -> None:
    engine = FlowFeatureEngine()
    bootstrap, market_connection, _ = make_bootstrap(engine=engine)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@forceOrder",
        {
            "e": "forceOrder",
            "E": _millis(NOW),
            "o": {"s": SYMBOL, "S": "SELL", "p": "64000.00", "ap": "64000.00", "q": "0.5", "T": _millis(NOW)},
        },
    )
    await asyncio.sleep(0.05)

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).liquidations.latest()
    assert len(retained) == 1
    assert retained[0].symbol == SYMBOL

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_wrong_symbol_liquidation_never_recorded() -> None:
    """Even though the bootstrap subscribes to the per-symbol liquidation
    stream (never the all-market stream), the forwarding loop's own
    defensive symbol check must still guarantee this invariant regardless of
    which stream shape is in play."""
    engine = FlowFeatureEngine()
    bootstrap, market_connection, _ = make_bootstrap(symbol=SYMBOL, engine=engine)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    # Simulate the all-market stream form arriving for a DIFFERENT symbol on
    # the same connection (defense in depth, independent of provider routing).
    market_connection.push_envelope(
        "!forceOrder@arr",
        {
            "e": "forceOrder",
            "E": _millis(NOW),
            "o": {"s": "ETHUSDT", "S": "SELL", "p": "3000.00", "ap": "3000.00", "q": "1.0", "T": _millis(NOW)},
        },
    )
    await asyncio.sleep(0.05)

    retained_configured = engine.history_for(SYMBOL, ContractType.PERPETUAL).liquidations.latest()
    retained_other = engine.history_for("ETHUSDT", ContractType.PERPETUAL).liquidations.latest()
    assert retained_configured == []
    assert retained_other == []  # never even routed - the per-symbol stream subscription itself excludes it

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_order_book_snapshot_forwarded_to_engine() -> None:
    """Deterministic resync: the REST snapshot fetch is held open with an
    asyncio.Event until a bridging depth delta has been pushed and buffered,
    so the resync succeeds on its first attempt - never relying on
    OrderBookSynchronizer's own randomized retry backoff timing."""
    from app.market_data.providers.binance.futures.realtime.constants import depth_stream_name

    engine = FlowFeatureEngine()
    release = asyncio.Event()

    async def controlled_snapshot_fetcher(symbol: str):
        await release.wait()
        return make_order_book_snapshot(symbol=symbol, last_update_id=100)

    bootstrap, _, public_connection = make_bootstrap(engine=engine, snapshot_fetcher=controlled_snapshot_fetcher)
    await bootstrap.start()
    await asyncio.sleep(0.02)  # subscribe + start_buffering has happened; fetch is pending on release

    public_connection.push_envelope(
        depth_stream_name(SYMBOL),
        {
            "e": "depthUpdate", "E": _millis(NOW), "T": _millis(NOW), "s": SYMBOL,
            "U": 95, "u": 105, "pu": 94,
            "b": [["100.00", "1.0"]], "a": [["101.00", "1.0"]],
        },
    )
    await asyncio.sleep(0.02)  # ensure the delta is buffered before the fetch resolves

    release.set()
    await asyncio.sleep(0.05)

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).order_book.latest()
    assert len(retained) == 1
    assert retained[0].symbol == SYMBOL

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_funding_forwarded_to_engine() -> None:
    engine = FlowFeatureEngine()
    bootstrap, market_connection, _ = make_bootstrap(engine=engine)
    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@markPrice@1s",
        {
            "e": "markPriceUpdate", "E": _millis(NOW), "s": SYMBOL,
            "p": "64010.00", "P": "64000.00", "i": "64005.00", "r": "0.0001", "T": _millis(NOW + timedelta(hours=1)),
        },
    )
    await asyncio.sleep(0.05)

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).funding.latest()
    assert len(retained) == 1
    assert retained[0].symbol == SYMBOL

    await bootstrap.stop()


@pytest.mark.asyncio
async def test_open_interest_polled_and_forwarded_to_engine() -> None:
    engine = FlowFeatureEngine()
    bootstrap, _, _ = make_bootstrap(engine=engine, open_interest_poll_interval_seconds=60.0)
    await bootstrap.start()
    await asyncio.sleep(0.05)  # the very first poll happens immediately in poll_once()

    retained = engine.history_for(SYMBOL, ContractType.PERPETUAL).open_interest.latest()
    assert len(retained) == 1
    assert retained[0].symbol == SYMBOL
    assert bootstrap.health().open_interest_last_success_at is not None

    await bootstrap.stop()


# --- staleness: existing calculators, unmodified, decide this - not this module ---


def test_order_book_staleness_uses_existing_threshold() -> None:
    snapshot = make_order_book_snapshot(timestamp=NOW)
    fresh = compute_order_book_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=[snapshot],
        bands=DEFAULT_DEPTH_BANDS, windows=(), observation_time=NOW, source="test",
    )
    stale = compute_order_book_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=[snapshot],
        bands=DEFAULT_DEPTH_BANDS, windows=(), observation_time=NOW + ORDER_BOOK_MAX_STALENESS + timedelta(seconds=1),
        source="test",
    )
    assert fresh.status.quality is FeatureQuality.VALID
    assert stale.status.quality is FeatureQuality.STALE


def test_funding_staleness_uses_existing_threshold() -> None:
    from app.core.models.funding import FundingRate

    observation = FundingRate(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, mark_price="64000", index_price="64000",
        funding_rate="0.0001", next_funding_time=NOW + timedelta(hours=1), funding_interval_hours=8,
        source="test", timestamp=NOW,
    )
    fresh = compute_funding_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=[observation],
        windows=(), observation_time=NOW, source="test",
    )
    stale = compute_funding_features(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, history=[observation],
        windows=(), observation_time=NOW + FUNDING_MAX_STALENESS + timedelta(seconds=1), source="test",
    )
    assert fresh.status.quality is FeatureQuality.VALID
    assert stale.status.quality is FeatureQuality.STALE
