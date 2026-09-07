"""MANUAL, OPERATOR-ONLY live check of the Stage 0A Flow production chain.

NOT part of the pytest suite: it needs internet access and opens real
WebSocket/REST connections to Binance's public USD-M futures endpoints (no
API key). Run it by hand to confirm the full chain still speaks to the real
venue:

    python scripts/check_flow_realtime_bootstrap.py
    python scripts/check_flow_realtime_bootstrap.py --symbol ETHUSDT --seconds 30

Exercises, within a bounded time budget:

    real Binance Futures realtime
    -> FlowFeatureEngine (existing, unmodified)
    -> the six existing, unmodified Flow analysts
    -> FlowSupervisor (existing, unmodified)
    -> a production FlowSupervisorResult

No trading action of any kind is taken: this script never constructs a
broker adapter, never calls a deterministic runtime-cycle orchestration
boundary, never calls an LLM explanation provider, and exposes no HTTP or
bot delivery surface. It only starts the Stage 0A realtime bootstrap,
prints operational health plus a concise summary of the production Flow
result, and shuts down cleanly on completion or Ctrl+C.

This script is optional and is never required for, or executed by, the
automated test suite. It is not run automatically by this implementation
pass - it is left for the operator/reviewer to run by hand afterward.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums.instrument import ContractType  # noqa: E402
from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig  # noqa: E402
from app.market_data.exceptions import MarketDataError  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT", help="symbol to inspect")
    parser.add_argument("--seconds", type=float, default=20.0, help="time budget for the whole check")
    return parser.parse_args()


async def _run(symbol: str, seconds: float) -> int:
    config = FlowRealtimeBootstrapConfig(symbol=symbol, contract_type=ContractType.PERPETUAL)
    bootstrap = FlowRealtimeBootstrap(config=config)

    stop_requested = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_requested.set)
        except NotImplementedError:
            pass  # signal handlers are not available on this platform (e.g. some Windows setups)

    print(f"flow realtime bootstrap live check: {symbol} (budget {seconds:.0f}s)")
    await bootstrap.start()
    try:
        try:
            await asyncio.wait_for(stop_requested.wait(), timeout=seconds)
            print("stop requested (Ctrl+C) - shutting down")
        except TimeoutError:
            pass

        health = bootstrap.health()
        print(f"market stream health:      {health.market.status.value}")
        print(f"order book stream health:  {health.order_book.status.value}")
        print(f"open interest last poll:   attempted={health.open_interest_last_attempt_at}, succeeded={health.open_interest_last_success_at}")
        print(f"funding interval (hours):  {bootstrap.funding_interval_hours()}")
        print("task health:")
        for label, task_health in (
            ("market_transport", health.market_transport_task),
            ("public_transport", health.public_transport_task),
            ("trades", health.trades_task),
            ("liquidations", health.liquidations_task),
            ("order_book", health.order_book_task),
            ("funding", health.funding_task),
            ("funding_cache_refresh", health.funding_cache_refresh_task),
            ("open_interest", health.open_interest_task),
        ):
            suffix = f" ({task_health.exception_type})" if task_health.exception_type else ""
            print(f"  {label:<24} {task_health.state.value}{suffix}")

        result = bootstrap.build_flow_result(as_of=datetime.now(UTC))
        print(f"flow supervisor outcome:   {result.outcome.value}")
        print(f"analyzed analysts:         {[a.value for a in result.analyzed_analysts]}")
        print(f"abstained analysts:        {[a.value for a in result.abstained_analysts]}")
        print(f"missing analysts:          {[a.value for a in result.missing_analysts]}")
        print(f"overall quality:           {result.overall_quality.value}")
        return 0
    finally:
        await bootstrap.stop()


def main() -> int:
    args = _parse_args()
    try:
        return asyncio.run(asyncio.wait_for(_run(args.symbol, args.seconds), timeout=args.seconds + 15))
    except MarketDataError as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    except (OSError, TimeoutError) as failure:
        print(f"FAILED: {type(failure).__name__}: {failure}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
