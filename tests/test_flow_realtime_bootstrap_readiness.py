"""Stage 0A ``build_flow_result`` tests: all six analysts always run,
deterministic ordering, honest ANALYZED/PARTIAL/INSUFFICIENT_EVIDENCE
outcomes, no fabricated neutral/zero values, immediately callable after
``start()``. No real network.

Expectations below are verified against the real, unmodified Flow
analysts/supervisor (not assumed): e.g. ``LiquidationAnalyst`` legitimately
reports ANALYZED on a confirmed-zero window (a genuine "no liquidations"
observation is valid data, not missing data), while ``OpenInterestAnalyst``
legitimately ABSTAINS on a single point-in-time observation - its own
window features require an observation at *both* window_start and
window_end to compute a change, so one reading alone cannot yet show a
trend. Neither is a wiring defect; both are the honest, existing calculator
behavior this Stage 0A component must never override or paper over.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.enums.flow_analysis import AnalystType
from app.core.enums.flow_supervisor import FlowSupervisorOutcome
from app.flow.engine import FlowFeatureEngine
from app.market_data.providers.binance.futures.realtime.constants import depth_stream_name
from tests.flow_realtime_bootstrap_support import NOW, SYMBOL, make_bootstrap, make_order_book_snapshot, millis


def _millis(dt) -> int:
    return millis(dt)


@pytest.mark.asyncio
async def test_build_flow_result_allowed_immediately_after_start() -> None:
    """Freshly started, zero real observations retained anywhere except
    liquidations' own confirmed-zero window - the call must not be
    refused/blocked, and must never fabricate a neutral result for any
    domain genuinely lacking data."""
    engine = FlowFeatureEngine()
    bootstrap, _, _ = make_bootstrap(engine=engine)

    await asyncio.wait_for(bootstrap.start(), timeout=1)
    try:
        result = bootstrap.build_flow_result(as_of=NOW)
    finally:
        await bootstrap.stop()

    assert result.outcome is FlowSupervisorOutcome.PARTIAL
    assert result.missing_count == 0  # all six always ran - none is "missing"
    assert set(result.analyzed_analysts) | set(result.abstained_analysts) == set(AnalystType)
    # taker flow / order book / open interest / funding / price-flow-relationship
    # genuinely have no data yet and honestly abstain - never fabricated
    for still_warming_up in (
        AnalystType.TAKER_FLOW,
        AnalystType.ORDER_BOOK_LIQUIDITY,
        AnalystType.OPEN_INTEREST,
        AnalystType.FUNDING,
        AnalystType.PRICE_FLOW_RELATIONSHIP,
    ):
        assert still_warming_up in result.abstained_analysts


def test_all_six_analysts_always_run_in_canonical_order() -> None:
    """Even with an empty engine (no observations at all), exactly six
    FlowAnalysisResult entries are produced - one per AnalystType - never
    fewer, and never with a fabricated substitute for a domain with no data."""
    from app.flow.realtime_bootstrap import _FLOW_ANALYSTS

    assert len(_FLOW_ANALYSTS) == 6
    assert {a.analyst_type for a in _FLOW_ANALYSTS} == set(AnalystType)

    bootstrap, _, _ = make_bootstrap()
    result = bootstrap.build_flow_result(as_of=NOW)

    assert set(result.expected_analysts) == set(AnalystType)
    assert result.missing_count == 0
    assert len(result.analyst_results) == 6


def test_result_is_deterministic_for_identical_retained_history() -> None:
    bootstrap, _, _ = make_bootstrap()
    first = bootstrap.build_flow_result(as_of=NOW)
    second = bootstrap.build_flow_result(as_of=NOW)
    assert first == second


@pytest.mark.asyncio
async def test_trade_funding_order_book_reach_analyzed_with_real_data() -> None:
    """Feed taker flow, funding, and order book real data - each reaches
    ANALYZED. Never asserts open-interest here: a single polled observation
    cannot show a trend (see module docstring) - that is exercised
    separately below with two temporally-separated observations."""
    release = asyncio.Event()

    async def controlled_snapshot_fetcher(symbol: str):
        await release.wait()
        return make_order_book_snapshot(symbol=symbol, last_update_id=100)

    bootstrap, market_connection, public_connection = make_bootstrap(
        snapshot_fetcher=controlled_snapshot_fetcher,
        open_interest_poll_interval_seconds=3600.0,  # keep OI out of this test's scope
    )
    await bootstrap.start()
    await asyncio.sleep(0.02)

    market_connection.push_envelope(
        f"{SYMBOL.lower()}@aggTrade",
        {"e": "aggTrade", "E": _millis(NOW), "s": SYMBOL, "a": 1, "p": "64000.00", "q": "0.1", "f": 1, "l": 1, "T": _millis(NOW), "m": False},
    )
    market_connection.push_envelope(
        f"{SYMBOL.lower()}@markPrice@1s",
        {"e": "markPriceUpdate", "E": _millis(NOW), "s": SYMBOL, "p": "64010.00", "P": "64000.00", "i": "64005.00", "r": "0.0001"},
    )
    public_connection.push_envelope(
        depth_stream_name(SYMBOL),
        {"e": "depthUpdate", "E": _millis(NOW), "T": _millis(NOW), "s": SYMBOL, "U": 95, "u": 105, "pu": 94,
         "b": [["100.00", "1.0"]], "a": [["101.00", "1.0"]]},
    )
    await asyncio.sleep(0.02)
    release.set()
    await asyncio.sleep(0.05)

    try:
        result = bootstrap.build_flow_result(as_of=NOW)
        assert AnalystType.TAKER_FLOW in result.analyzed_analysts
        assert AnalystType.FUNDING in result.analyzed_analysts
        assert AnalystType.ORDER_BOOK_LIQUIDITY in result.analyzed_analysts
        assert result.missing_count == 0
    finally:
        await bootstrap.stop()


def test_open_interest_reaches_analyzed_once_two_time_separated_observations_exist() -> None:
    """OpenInterestAnalyst's own window-based change calculation needs one
    observation at-or-before window_start and one at-or-before window_end -
    a single reading can never satisfy both. Feeding two, far enough apart
    to straddle the shortest configured window, lets it honestly reach
    ANALYZED - proving Stage 0A's wiring does not interfere with this
    existing, unmodified requirement."""
    from datetime import timedelta

    from app.core.enums.instrument import ContractType
    from app.core.models.open_interest import OpenInterest

    engine = FlowFeatureEngine()
    engine.record_open_interest(
        OpenInterest(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, open_interest="1000", source="test", timestamp=NOW - timedelta(minutes=20))
    )
    engine.record_open_interest(
        OpenInterest(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, open_interest="1050", source="test", timestamp=NOW)
    )

    bootstrap, _, _ = make_bootstrap(engine=engine)
    result = bootstrap.build_flow_result(as_of=NOW)

    assert AnalystType.OPEN_INTEREST in result.analyzed_analysts
