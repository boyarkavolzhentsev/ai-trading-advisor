"""Stage 0A single-event-loop concurrency invariant tests (see the
``app.flow.realtime_bootstrap`` module docstring for the full statement of
the invariant this file guards).

No lock protects ``FlowFeatureEngine`` anywhere in Stage 0A. That is only
safe because:

1. ``FlowFeatureEngine.record_*``/``build_snapshot`` are plain synchronous,
   non-``async`` methods with no ``await`` inside them;
2. engine mutation/reads are never executed via ``asyncio.to_thread`` or any
   other thread - only the genuinely blocking REST calls are.

This file regression-tests both structural preconditions directly, plus a
live interleaving test demonstrating no torn/partial state results from
concurrent engine access under asyncio's cooperative scheduling.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.trade_event import TradeEvent
from app.flow import open_interest_poller
from app.flow.engine import FlowFeatureEngine
from tests.flow_realtime_bootstrap_support import NOW, SYMBOL


def test_engine_record_methods_are_not_coroutine_functions() -> None:
    engine = FlowFeatureEngine()
    for name in ("record_trade", "record_liquidation", "record_order_book", "record_open_interest", "record_funding"):
        method = getattr(engine, name)
        assert not inspect.iscoroutinefunction(method), f"{name} must remain synchronous"


def test_engine_build_snapshot_is_not_a_coroutine_function() -> None:
    engine = FlowFeatureEngine()
    assert not inspect.iscoroutinefunction(engine.build_snapshot)


def test_open_interest_poller_never_passes_record_call_into_a_thread() -> None:
    """AST-scan: the only argument ever passed to asyncio.to_thread in this
    module must be the provider's get_open_interest bound method - never
    anything touching the engine."""
    source = textwrap.dedent(inspect.getsource(open_interest_poller))
    tree = ast.parse(source)

    to_thread_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
    ]
    assert to_thread_calls, "expected at least one asyncio.to_thread call"
    for call in to_thread_calls:
        assert call.args, "to_thread call must pass an explicit callable"
        first_arg_source = ast.dump(call.args[0])
        assert "engine" not in first_arg_source.lower(), "engine must never be touched from a worker thread"


def test_engine_mutation_never_wrapped_in_to_thread_anywhere_in_module_source() -> None:
    """Belt-and-suspenders textual check across the whole module: a
    'record_' call must never appear as a to_thread argument."""
    source = inspect.getsource(open_interest_poller)
    for line in source.splitlines():
        if "to_thread" in line:
            assert "record_" not in line


async def _record_many_trades(engine: FlowFeatureEngine, *, count: int) -> None:
    for i in range(count):
        engine.record_trade(
            TradeEvent(
                symbol=SYMBOL, contract_type=ContractType.PERPETUAL, trade_id=i,
                price=Decimal("64000"), quantity=Decimal("0.01"), quote_quantity=Decimal("640"),
                side=OrderSide.BUY, timestamp=NOW, source="test",
            )
        )
        await asyncio.sleep(0)  # force a scheduling point between synchronous writes


async def _read_snapshots_repeatedly(engine: FlowFeatureEngine, *, count: int) -> list[int]:
    counts: list[int] = []
    for _ in range(count):
        snapshot = engine.build_snapshot(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, observation_time=NOW)
        history = engine.history_for(SYMBOL, ContractType.PERPETUAL)
        counts.append(len(history.trades.latest()))
        assert snapshot.symbol == SYMBOL  # never a torn/partial snapshot
        await asyncio.sleep(0)
    return counts


async def _run_interleaved_engine_access() -> None:
    engine = FlowFeatureEngine()
    write_task = asyncio.create_task(_record_many_trades(engine, count=50))
    read_task = asyncio.create_task(_read_snapshots_repeatedly(engine, count=50))
    await asyncio.gather(write_task, read_task)

    # final state must be exactly 50 trades - no lost/duplicated write from
    # interleaving, no exception raised by either task
    history = engine.history_for(SYMBOL, ContractType.PERPETUAL)
    assert len(history.trades.latest()) == 50


def test_concurrent_record_and_build_snapshot_never_produce_torn_state() -> None:
    asyncio.run(_run_interleaved_engine_access())
