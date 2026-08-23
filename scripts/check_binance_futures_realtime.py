"""Manual live check of the Binance USD-M futures real-time WebSocket layer.

NOT part of the pytest suite: it needs internet access and opens real
WebSocket connections to Binance's public USD-M futures streams (no API
key). Run it by hand to confirm the Stage 1C wiring still speaks to the real
venue:

    python scripts/check_binance_futures_realtime.py
    python scripts/check_binance_futures_realtime.py --symbol ETHUSDT --seconds 20

It exercises, within a bounded time budget:

- aggTrade (taker buy/sell prints)
- mark price / funding rate
- the all-market liquidation stream (subscription only - a liquidation
  event may legitimately never arrive during a short run; that is not a
  failure, see Stage 1C decision 8)
- order-book synchronization (REST snapshot + buffered/live depth deltas)

Exits with code 0 on success and 1 with a clear reason if Binance is
unreachable or the connection fails outright. This script is optional and
is never required for the automated test suite.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.market_data.exceptions import MarketDataError  # noqa: E402
from app.market_data.providers.binance.client import BinanceRestClient  # noqa: E402
from app.market_data.providers.binance.futures.provider import (  # noqa: E402
    BinanceFuturesMarketDataProvider,
)
from app.market_data.providers.binance.futures.realtime import (  # noqa: E402
    BinanceFuturesMarketStream,
    BinanceFuturesOrderBookStream,
    FundingIntervalCache,
    make_binance_fetch_all,
    make_market_transport,
    make_public_transport,
    make_snapshot_fetcher,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT", help="symbol to inspect")
    parser.add_argument("--seconds", type=float, default=15.0, help="time budget for the whole check")
    return parser.parse_args()


async def _collect_one(label: str, iterator, seconds: float) -> object | None:
    try:
        return await asyncio.wait_for(anext(iterator), timeout=seconds)
    except TimeoutError:
        print(f"{label:<12} no event within {seconds:.0f}s (subscription only, not necessarily a failure)")
        return None


async def _run(symbol: str, seconds: float) -> int:
    rest_client = BinanceRestClient()
    rest_provider = BinanceFuturesMarketDataProvider(rest_client)
    funding_cache = FundingIntervalCache(make_binance_fetch_all(rest_client))
    await funding_cache.refresh_if_stale()

    market_transport = make_market_transport()
    public_transport = make_public_transport()
    market_stream = BinanceFuturesMarketStream(market_transport, funding_interval_cache=funding_cache)
    order_book_stream = BinanceFuturesOrderBookStream(
        public_transport, snapshot_fetcher=make_snapshot_fetcher(rest_provider)
    )

    market_task = asyncio.create_task(market_transport.run())
    public_task = asyncio.create_task(public_transport.run())
    market_stream.start()
    order_book_stream.start()

    try:
        trades = market_stream.trades(symbol)
        mark_prices = market_stream.mark_price(symbol)
        liquidations = market_stream.liquidations()
        books = order_book_stream.order_book(symbol)

        budget = max(1.0, seconds / 4)
        trade = await _collect_one("agg trade", trades, budget)
        if trade is not None:
            print(f"agg trade    {trade.symbol} side={trade.side.value} qty={trade.quantity} @ {trade.price}")

        funding = await _collect_one("mark price", mark_prices, budget)
        if funding is not None:
            interval = (
                f"{funding.funding_interval_hours}h" if funding.funding_interval_hours is not None
                else "unknown"
            )
            print(f"mark price   {funding.symbol} rate={funding.funding_rate} interval={interval}")

        book = await _collect_one("order book", books, budget)
        if book is not None:
            best_bid = book.bids[0] if book.bids else None
            best_ask = book.asks[0] if book.asks else None
            print(f"order book   last_update_id={book.last_update_id} bid={best_bid} ask={best_ask}")

        await _collect_one("liquidation", liquidations, budget)

        market_health = market_stream.health()
        book_health = order_book_stream.health()
        print(f"health       market={market_health.status.value} order_book={book_health.status.value}")

        if trade is None and funding is None and book is None:
            print("FAILED: no data received on any stream", file=sys.stderr)
            return 1
        print("OK")
        return 0
    finally:
        await market_stream.stop()
        await order_book_stream.stop()
        await market_transport.stop()
        await public_transport.stop()
        for task in (market_task, public_task):
            task.cancel()
        rest_client.close()


def main() -> int:
    args = _parse_args()
    print(f"binance futures real-time live check: {args.symbol} (budget {args.seconds:.0f}s)")
    try:
        return asyncio.run(asyncio.wait_for(_run(args.symbol, args.seconds), timeout=args.seconds + 10))
    except MarketDataError as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    except (OSError, TimeoutError) as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
