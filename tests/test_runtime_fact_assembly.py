"""``assemble_account_risk_snapshot`` - success mapping, fail-closed upstream
unavailability, multi-failure accumulation, and as_of/timestamp coherence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.mt5_rollover import MT5RolloverOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason, RuntimeFactAssemblyOutcome
from app.orchestration.facts import assemble_account_risk_snapshot
from tests.runtime_fact_assembly_support import (
    AS_OF,
    TRADING_DAY_KEY,
    blocked_open_risk,
    blocked_realized_pnl,
    rollover_bootstrapped_midday,
    rollover_ready,
    rollover_unusable,
    usable_open_risk,
    usable_realized_pnl,
)


def _assemble(*, rollover=None, pnl=None, risk=None, as_of=AS_OF):
    return assemble_account_risk_snapshot(
        as_of=as_of,
        rollover_snapshot=rollover if rollover is not None else rollover_ready(),
        realized_daily_pnl_assessment=pnl if pnl is not None else usable_realized_pnl(),
        open_risk_assessment=risk if risk is not None else usable_open_risk(),
    )


# --- SUCCESS ---


def test_exact_field_mapping_into_account_risk_snapshot() -> None:
    rollover = rollover_ready(rollover_equity=Decimal("100000"), current_equity=Decimal("101234.5678"), floating_pnl=Decimal("-12.34"))
    pnl = usable_realized_pnl(realized_daily_pnl=Decimal("567.89"))
    risk = usable_open_risk(current_open_risk_to_stop=Decimal("321.09"))

    result = _assemble(rollover=rollover, pnl=pnl, risk=risk)

    assert result.outcome is RuntimeFactAssemblyOutcome.READY
    snapshot = result.account_snapshot
    assert snapshot.as_of == AS_OF
    assert snapshot.rollover_equity == Decimal("100000")
    assert snapshot.current_equity == Decimal("101234.5678")
    assert snapshot.realized_daily_pnl == Decimal("567.89")
    assert snapshot.floating_pnl == Decimal("-12.34")
    assert snapshot.current_open_risk_to_stop == Decimal("321.09")


def test_decimal_values_preserved_exactly_high_precision() -> None:
    rollover = rollover_ready(rollover_equity=Decimal("100000.123456789"), current_equity=Decimal("100500.987654321"))
    result = _assemble(rollover=rollover)
    assert result.account_snapshot.rollover_equity == Decimal("100000.123456789")
    assert result.account_snapshot.current_equity == Decimal("100500.987654321")


def test_positive_realized_pnl() -> None:
    result = _assemble(pnl=usable_realized_pnl(realized_daily_pnl=Decimal("500")))
    assert result.account_snapshot.realized_daily_pnl == Decimal("500")


def test_negative_realized_pnl() -> None:
    result = _assemble(pnl=usable_realized_pnl(realized_daily_pnl=Decimal("-500")))
    assert result.account_snapshot.realized_daily_pnl == Decimal("-500")


def test_positive_floating_pnl() -> None:
    result = _assemble(rollover=rollover_ready(floating_pnl=Decimal("75")))
    assert result.account_snapshot.floating_pnl == Decimal("75")


def test_negative_floating_pnl() -> None:
    result = _assemble(rollover=rollover_ready(floating_pnl=Decimal("-75")))
    assert result.account_snapshot.floating_pnl == Decimal("-75")


def test_zero_open_risk() -> None:
    result = _assemble(risk=usable_open_risk(current_open_risk_to_stop=Decimal("0")))
    assert result.account_snapshot.current_open_risk_to_stop == Decimal("0")


def test_nonzero_open_risk() -> None:
    result = _assemble(risk=usable_open_risk(current_open_risk_to_stop=Decimal("999.99")))
    assert result.account_snapshot.current_open_risk_to_stop == Decimal("999.99")


def test_bootstrapped_midday_rollover_is_usable() -> None:
    rollover = rollover_bootstrapped_midday(rollover_equity=Decimal("77000"))
    result = _assemble(rollover=rollover)
    assert result.outcome is RuntimeFactAssemblyOutcome.READY
    assert result.account_snapshot.rollover_equity == Decimal("77000")


# --- FAIL CLOSED ---


@pytest.mark.parametrize(
    "outcome",
    [
        MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE,
        MT5RolloverOutcome.PERSISTENCE_CORRUPT,
        MT5RolloverOutcome.CONFIG_MISMATCH,
        MT5RolloverOutcome.FUTURE_STATE,
    ],
)
def test_every_non_usable_rollover_outcome_blocks(outcome: MT5RolloverOutcome) -> None:
    result = _assemble(rollover=rollover_unusable(outcome=outcome))
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE in result.reasons
    assert result.account_snapshot is None


def test_realized_pnl_blocked_outcome_blocks() -> None:
    result = _assemble(pnl=blocked_realized_pnl())
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.REALIZED_PNL_UNAVAILABLE,)


def test_open_risk_blocked_outcome_blocks() -> None:
    result = _assemble(risk=blocked_open_risk())
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.OPEN_RISK_UNAVAILABLE,)


def test_multiple_simultaneous_failures_accumulate() -> None:
    result = _assemble(
        rollover=rollover_unusable(outcome=MT5RolloverOutcome.PERSISTENCE_CORRUPT),
        pnl=blocked_realized_pnl(),
        risk=blocked_open_risk(),
    )
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (
        RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE,
        RuntimeFactAssemblyBlockReason.REALIZED_PNL_UNAVAILABLE,
        RuntimeFactAssemblyBlockReason.OPEN_RISK_UNAVAILABLE,
    )  # canonical declaration order, deterministic, not a precedence winner


def test_unavailable_positions_never_fabricates_zero_open_risk() -> None:
    """BLOCKED open risk must never be silently substituted with a
    Decimal('0') - the assembly must block outright."""
    result = _assemble(risk=blocked_open_risk())
    assert result.account_snapshot is None
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED


def test_unavailable_history_never_fabricates_zero_realized_pnl() -> None:
    result = _assemble(pnl=blocked_realized_pnl())
    assert result.account_snapshot is None
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED


def test_unavailable_rollover_never_falls_back_to_current_equity() -> None:
    """A BLOCKED rollover must never let current_equity stand in for
    rollover_equity - the assembly must block outright, not substitute."""
    result = _assemble(rollover=rollover_unusable(outcome=MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE))
    assert result.account_snapshot is None
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED


# --- TIMING ---


def test_caller_as_of_preserved_exactly_on_success() -> None:
    custom_as_of = datetime(2026, 3, 15, 9, 30, 0, tzinfo=UTC)
    result = assemble_account_risk_snapshot(
        as_of=custom_as_of,
        rollover_snapshot=rollover_ready(as_of=custom_as_of),
        realized_daily_pnl_assessment=usable_realized_pnl(as_of=custom_as_of),
        open_risk_assessment=usable_open_risk(as_of=custom_as_of),
    )
    assert result.as_of == custom_as_of
    assert result.account_snapshot.as_of == custom_as_of


def test_caller_as_of_preserved_exactly_on_blocked() -> None:
    custom_as_of = datetime(2026, 3, 15, 9, 30, 0, tzinfo=UTC)
    result = assemble_account_risk_snapshot(
        as_of=custom_as_of,
        rollover_snapshot=rollover_unusable(outcome=MT5RolloverOutcome.PERSISTENCE_CORRUPT, as_of=custom_as_of),
        realized_daily_pnl_assessment=usable_realized_pnl(as_of=custom_as_of),
        open_risk_assessment=usable_open_risk(as_of=custom_as_of),
    )
    assert result.as_of == custom_as_of


def test_rollover_as_of_mismatch_blocks_with_timestamp_mismatch() -> None:
    mismatched = rollover_ready(as_of=AS_OF - timedelta(minutes=1))
    result = _assemble(rollover=mismatched)
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH,)


def test_realized_pnl_as_of_mismatch_blocks_with_timestamp_mismatch() -> None:
    mismatched = usable_realized_pnl(as_of=AS_OF - timedelta(minutes=1))
    result = _assemble(pnl=mismatched)
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH,)


def test_open_risk_as_of_mismatch_blocks_with_timestamp_mismatch() -> None:
    mismatched = usable_open_risk(as_of=AS_OF - timedelta(minutes=1))
    result = _assemble(risk=mismatched)
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH,)


def test_trading_day_key_mismatch_between_rollover_and_realized_pnl_blocks() -> None:
    """Same as_of on all three, but rollover_state.trading_day_key
    disagrees with the realized-PnL assessment's own trading_day_key - a
    genuine coherence defect distinct from any single upstream outcome
    being unusable."""
    rollover = rollover_ready(trading_day_key="2026-01-01")
    pnl = usable_realized_pnl(trading_day_key="2025-12-31")
    result = _assemble(rollover=rollover, pnl=pnl)
    assert result.outcome is RuntimeFactAssemblyOutcome.BLOCKED
    assert result.reasons == (RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH,)


def test_matching_trading_day_key_does_not_block() -> None:
    rollover = rollover_ready(trading_day_key=TRADING_DAY_KEY)
    pnl = usable_realized_pnl(trading_day_key=TRADING_DAY_KEY)
    result = _assemble(rollover=rollover, pnl=pnl)
    assert result.outcome is RuntimeFactAssemblyOutcome.READY


def test_no_wall_clock_call_required_as_of_is_purely_caller_supplied() -> None:
    """Calling twice with two different explicit as_of values, all inputs
    otherwise identical, must reflect exactly the supplied as_of each time -
    proving the function never substitutes its own clock reading."""
    first = assemble_account_risk_snapshot(
        as_of=AS_OF, rollover_snapshot=rollover_ready(), realized_daily_pnl_assessment=usable_realized_pnl(), open_risk_assessment=usable_open_risk()
    )
    other_as_of = AS_OF + timedelta(days=10)
    second = assemble_account_risk_snapshot(
        as_of=other_as_of,
        rollover_snapshot=rollover_ready(as_of=other_as_of),
        realized_daily_pnl_assessment=usable_realized_pnl(as_of=other_as_of),
        open_risk_assessment=usable_open_risk(as_of=other_as_of),
    )
    assert first.as_of == AS_OF
    assert second.as_of == other_as_of
