"""Manual live check of the Binance market data provider.

NOT part of the pytest suite: it needs internet access and hits the public
Binance Spot REST API (no API key). Run it by hand when you want to confirm the
adapter still speaks to the real venue:

    python scripts/check_binance_market_data.py
    python scripts/check_binance_market_data.py --symbol ETHUSDT --candles 3

Exits with code 0 on success and 1 with a single-line reason when the venue is
unreachable or answers something unusable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import Timeframe  # noqa: E402
from app.market_data.exceptions import MarketDataError  # noqa: E402
from app.market_data.providers.binance import (  # noqa: E402
    BINANCE_SPOT_BASE_URL,
    BinanceMarketDataProvider,
    BinanceRestClient,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT", help="symbol to inspect")
    parser.add_argument(
        "--timeframe",
        default=Timeframe.M5.value,
        choices=[Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1],
        help="candle timeframe",
    )
    parser.add_argument("--candles", type=int, default=5, help="number of candles to print")
    parser.add_argument("--base-url", default=BINANCE_SPOT_BASE_URL, help="REST base URL")
    return parser.parse_args()


def _report(provider: BinanceMarketDataProvider, args: argparse.Namespace) -> None:
    symbol = args.symbol
    timeframe = Timeframe(args.timeframe)

    price = provider.get_current_price(symbol)
    print(f"price      {price.symbol} {price.price} at {price.timestamp.isoformat()}")

    quote = provider.get_bid_ask(symbol)
    print(
        f"bid/ask    {quote.bid} / {quote.ask}  spread {quote.spread}  "
        f"sizes {quote.bid_quantity} / {quote.ask_quantity}"
    )

    candles = provider.get_ohlcv(symbol, timeframe, limit=args.candles)
    print(f"candles    last {len(candles)} x {timeframe.value}")
    for candle in candles:
        print(
            f"  {candle.timestamp.isoformat()}  O {candle.open}  H {candle.high}  "
            f"L {candle.low}  C {candle.close}  V {candle.volume}"
        )

    metadata = provider.get_instrument_metadata(symbol)
    print(
        f"metadata   {metadata.symbol} {metadata.base_asset}/{metadata.quote_asset} "
        f"status={metadata.status.value}"
    )
    print(
        f"           tick={metadata.tick_size} (precision {metadata.price_precision})  "
        f"step={metadata.step_size} (precision {metadata.quantity_precision})"
    )
    print(
        f"           qty {metadata.min_quantity} .. {metadata.max_quantity}  "
        f"min_notional={metadata.min_notional}"
    )


def main() -> int:
    args = _parse_args()
    print(f"binance live check: {args.symbol} via {args.base_url}")
    try:
        with BinanceRestClient(base_url=args.base_url) as client:
            _report(BinanceMarketDataProvider(client), args)
    except MarketDataError as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
