"""Manual Phase 1 live MT5 read-only smoke check (V1 Live Read-Only Smoke
Preparation).

NOT part of the pytest suite: it needs a running, already-authenticated MT5
terminal and performs real read-only calls against it. Run it by hand only
after separate approval to begin Phase 1 - never automatically, never from
CI, never as a side effect of running this repository's test suite:

    python scripts/check_mt5_readonly.py
    python scripts/check_mt5_readonly.py --symbol BTCUSDt

Validates only: ``initialize``, ``runtime_status``, ``account_facts``,
``positions``, ``symbol_facts``/quote, ``shutdown`` - nothing else. No OHLCV
(Phase 2), no Binance (Phase 3), no production ``run_cycle`` (Phase 4/5), no
LLM, no tracking/provenance writes.

Structurally incapable of trading: the only MT5-facing calls in this file
are the six ``MT5ClientProtocol`` methods named above. That protocol
(``app/mt5/protocols.py``) documents itself as "Deliberately exclud[ing] any
order-placement method" - there is no order/execution method on it to call
even in principle, so this harness cannot open, modify, or cancel a broker
order by construction, not merely by discipline.

Credentials/session come only from the existing production bootstrap
mechanism (``app.bootstrap.production.build_mt5_readonly_config_from_env``)
- never a new ad hoc credential-reading scheme, and never a CLI secret
argument. ``app/bootstrap/production.py`` is documented as the one module
allowed to construct ``MT5Credentials``, so this script goes through it
rather than building credentials itself; ``build_mt5_readonly_config_from_env``
is that module's own narrow, MT5-only counterpart to its full
``build_production_advisory_config_from_env`` - reusing the same
``_build_mt5_credentials()`` helper internally, so there is exactly one
credential-parsing implementation in this repository, never a second - and
it requires only ``ADVISORY_MT5_SYMBOL`` plus the already-optional MT5
path/credential variables, never the unrelated Binance/calendar/market
configuration a full production cycle needs but this read-only check does
not. No credential value, account/login identity, broker password, or raw
environment is ever read or printed by this file.

Exits 0 on PASS, 1 on FAIL (including any unexpected exception).
``run_mt5_readonly_smoke`` always calls ``shutdown()`` via ``finally``,
regardless of outcome - mirroring ``ProductionAdvisoryComposer.run_cycle``'s
own one-initialize/one-shutdown-per-attempt guarantee.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap.production import BootstrapConfigurationError, build_mt5_readonly_config_from_env  # noqa: E402
from app.core.enums.mt5_runtime import MT5ConnectivityState  # noqa: E402
from app.mt5.client import MT5Client  # noqa: E402
from app.mt5.protocols import MT5ClientProtocol  # noqa: E402


@dataclass(frozen=True)
class MT5ReadOnlySmokeResult:
    """Every fact this check observed, plus the derived PASS/FAIL verdict.
    Deliberately carries no account/login identity, no credential, and no
    raw broker object - only the fields the audit's own safe-output list
    allows (see this module's own docstring and the V1 Live Read-Only Smoke
    Preparation report, section 4)."""

    symbol: str
    initialize_state: MT5ConnectivityState
    runtime_status_state: MT5ConnectivityState | None
    account_facts_available: bool
    account_currency: str | None
    positions_status: str
    position_count: int | None
    symbol_facts_available: bool
    bid: Decimal | None
    ask: Decimal | None
    spread: Decimal | None
    point: Decimal | None
    trade_stops_level: int | None
    trade_tick_size: Decimal | None
    trade_tick_value_loss: Decimal | None
    volume_min: Decimal | None
    volume_max: Decimal | None
    volume_step: Decimal | None
    passed: bool
    failure_reasons: tuple[str, ...]


def run_mt5_readonly_smoke(client: MT5ClientProtocol, *, symbol: str) -> MT5ReadOnlySmokeResult:
    """Pure Phase 1 proof over any ``MT5ClientProtocol``-typed client (a real
    ``MT5Client`` in production use, any structurally-compatible fake in
    tests): ``initialize()`` -> (only if ``AVAILABLE``) ``runtime_status()``
    -> ``account_facts()`` -> ``positions()`` -> ``symbol_facts(symbol)`` ->
    always ``shutdown()``, via ``finally``, regardless of outcome or any
    exception raised along the way.

    Never raises for a legitimate broker/terminal/account condition - every
    such condition becomes a ``failure_reasons`` entry and
    ``passed=False``, mirroring ``MT5Client``'s own typed-state-not-
    exception philosophy. A genuinely unexpected exception (a caller-
    contract violation, not a broker condition) is deliberately left to
    propagate to the caller after ``shutdown()`` has still run - never
    silently swallowed here.
    """
    failures: list[str] = []
    initialize_state = MT5ConnectivityState.INITIALIZATION_FAILED
    runtime_status_state: MT5ConnectivityState | None = None
    account_facts_available = False
    account_currency: str | None = None
    positions_status = "UNAVAILABLE"
    position_count: int | None = None
    symbol_facts_available = False
    bid: Decimal | None = None
    ask: Decimal | None = None
    spread: Decimal | None = None
    point: Decimal | None = None
    trade_stops_level: int | None = None
    trade_tick_size: Decimal | None = None
    trade_tick_value_loss: Decimal | None = None
    volume_min: Decimal | None = None
    volume_max: Decimal | None = None
    volume_step: Decimal | None = None

    try:
        status = client.initialize()
        initialize_state = status.state
        if initialize_state is not MT5ConnectivityState.AVAILABLE:
            failures.append(f"initialize() did not return AVAILABLE (got {initialize_state.value})")
        else:
            reported = client.runtime_status()
            runtime_status_state = reported.state
            if runtime_status_state is not MT5ConnectivityState.AVAILABLE:
                failures.append(f"runtime_status() did not report AVAILABLE (got {runtime_status_state.value})")

            account_facts = client.account_facts()
            account_facts_available = account_facts is not None
            if account_facts is None:
                failures.append("account_facts() is None")
            else:
                account_currency = account_facts.currency

            positions_status, positions = client.positions()
            if positions_status != "OK":
                failures.append(f"positions() returned {positions_status!r}, expected 'OK'")
            else:
                position_count = len(positions)

            facts = client.symbol_facts(symbol)
            symbol_facts_available = facts is not None
            if facts is None:
                failures.append(f"symbol_facts({symbol!r}) is None")
            else:
                bid, ask, point = facts.bid, facts.ask, facts.point
                spread = facts.ask - facts.bid
                trade_stops_level = facts.trade_stops_level
                trade_tick_size = facts.trade_tick_size
                trade_tick_value_loss = facts.trade_tick_value_loss
                volume_min, volume_max, volume_step = facts.volume_min, facts.volume_max, facts.volume_step

                if not bid > 0:
                    failures.append("bid is not > 0")
                if not ask > bid:
                    failures.append("ask is not > bid")
                if not point > 0:
                    failures.append("point is not > 0")
                if not trade_tick_size > 0:
                    failures.append("trade_tick_size is not > 0")
                if not trade_tick_value_loss > 0:
                    failures.append("trade_tick_value_loss is not > 0")
                if not volume_min > 0:
                    failures.append("volume_min is not > 0")
                if not volume_max >= volume_min:
                    failures.append("volume_max is not >= volume_min")
                if not volume_step > 0:
                    failures.append("volume_step is not > 0")
    finally:
        client.shutdown()

    return MT5ReadOnlySmokeResult(
        symbol=symbol,
        initialize_state=initialize_state,
        runtime_status_state=runtime_status_state,
        account_facts_available=account_facts_available,
        account_currency=account_currency,
        positions_status=positions_status,
        position_count=position_count,
        symbol_facts_available=symbol_facts_available,
        bid=bid,
        ask=ask,
        spread=spread,
        point=point,
        trade_stops_level=trade_stops_level,
        trade_tick_size=trade_tick_size,
        trade_tick_value_loss=trade_tick_value_loss,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        passed=not failures,
        failure_reasons=tuple(failures),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--symbol",
        default=None,
        help="MT5 executable symbol to inspect (defaults to the configured ADVISORY_MT5_SYMBOL)",
    )
    return parser.parse_args()


def _print_report(result: MT5ReadOnlySmokeResult) -> None:
    print(f"mt5 read-only smoke check: {result.symbol}")
    print(f"initialize state             {result.initialize_state.value}")
    if result.runtime_status_state is not None:
        print(f"runtime_status state         {result.runtime_status_state.value}")
    print(f"account facts available      {result.account_facts_available}")
    if result.account_currency is not None:
        print(f"account currency             {result.account_currency}")
    print(f"positions status             {result.positions_status}")
    if result.position_count is not None:
        print(f"position count               {result.position_count}")
    print(f"symbol facts available       {result.symbol_facts_available}")
    if result.symbol_facts_available:
        print(f"bid / ask / spread           {result.bid} / {result.ask} / {result.spread}")
        print(f"point                        {result.point}")
        print(f"trade_stops_level            {result.trade_stops_level}")
        print(f"trade_tick_size              {result.trade_tick_size}")
        print(f"trade_tick_value_loss        {result.trade_tick_value_loss}")
        print(f"volume min / max / step      {result.volume_min} / {result.volume_max} / {result.volume_step}")
    for reason in result.failure_reasons:
        print(f"FAIL reason: {reason}", file=sys.stderr)
    print("PASS" if result.passed else "FAIL")


def main() -> int:
    args = _parse_args()

    try:
        config = build_mt5_readonly_config_from_env()
    except BootstrapConfigurationError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    symbol = args.symbol if args.symbol is not None else config.mt5_symbol
    client = MT5Client(path=config.mt5_path, credentials=config.mt5_credentials)

    try:
        result = run_mt5_readonly_smoke(client, symbol=symbol)
    except Exception as exc:  # a genuinely unexpected failure is a FAIL, never an unhandled crash with no exit code
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    _print_report(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
