"""Manual live check of the Binance USD-M futures market data provider.

NOT part of the pytest suite: it needs internet access and hits the public
Binance USD-M Futures REST API (no API key). Run it by hand when you want to
confirm the adapter still speaks to the real venue:

    python scripts/check_binance_futures_market_data.py
    python scripts/check_binance_futures_market_data.py --symbol ETHUSDT --candles 3

The liquidation stub is exercised too: it is expected to raise
``DataNotAvailableError`` (no public REST endpoint exists), and that is
reported as expected behaviour, not a failure.

Exits with code 0 on success and 1 with a single-line reason when the venue is
unreachable or answers something unusable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import Timeframe  # noqa: E402
from app.market_data.exceptions import DataNotAvailableError, MarketDataError  # noqa: E402
from app.market_data.providers.binance.client import BinanceRestClient  # noqa: E402
from app.market_data.providers.binance.futures import (  # noqa: E402
    BINANCE_FUTURES_BASE_URL,
    BinanceFuturesMarketDataProvider,
    BinanceRestLiquidationProvider,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT", help="symbol to inspect")
    parser.add_argument(
        "--timeframe",
        default=Timeframe.M5.value,
        choices=[Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1],
        help="taker flow candle timeframe",
    )
    parser.add_argument("--candles", type=int, default=5, help="number of taker flow candles to print")
    parser.add_argument("--depth", type=int, default=10, help="order book levels per side")
    parser.add_argument("--base-url", default=BINANCE_FUTURES_BASE_URL, help="REST base URL")
    return parser.parse_args()


def _report(provider: BinanceFuturesMarketDataProvider, args: argparse.Namespace) -> None:
    symbol = args.symbol
    timeframe = Timeframe(args.timeframe)

    funding = provider.get_funding_rate(symbol)
    interval = (
        f"{funding.funding_interval_hours}h" if funding.funding_interval_hours is not None else "unknown"
    )
    print(
        f"funding    {funding.symbol} rate={funding.funding_rate} interval={interval} "
        f"mark={funding.mark_price} index={funding.index_price} at {funding.timestamp.isoformat()}"
    )

    open_interest = provider.get_open_interest(symbol)
    print(f"open int.  {open_interest.symbol} {open_interest.open_interest} at {open_interest.timestamp.isoformat()}")

    flow = provider.get_taker_flow(symbol, timeframe, limit=args.candles)
    print(f"taker flow last {len(flow)} x {timeframe.value}")
    for snapshot in flow:
        print(
            f"  {snapshot.timestamp.isoformat()}  buy {snapshot.buy_volume}  sell {snapshot.sell_volume}  "
            f"total {snapshot.total_volume}  delta {snapshot.delta}  buy_ratio {snapshot.buy_ratio:.3f}"
        )

    book = provider.get_order_book_snapshot(symbol, limit=args.depth)
    print(f"order book last_update_id={book.last_update_id} at {book.timestamp.isoformat()}")
    best_bid = book.bids[0] if book.bids else None
    best_ask = book.asks[0] if book.asks else None
    print(f"           best bid {best_bid}  best ask {best_ask}")

    liquidations = BinanceRestLiquidationProvider()
    try:
        liquidations.get_recent_liquidations(symbol)
    except DataNotAvailableError as expected:
        print(f"liquidations  expected DataNotAvailableError: {expected}")


def main() -> int:
    args = _parse_args()
    print(f"binance futures live check: {args.symbol} via {args.base_url}")
    try:
        with BinanceRestClient(base_url=args.base_url) as client:
            _report(BinanceFuturesMarketDataProvider(client), args)
    except MarketDataError as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
