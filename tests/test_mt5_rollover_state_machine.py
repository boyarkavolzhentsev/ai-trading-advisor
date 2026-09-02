"""Stage 10B pure rollover decision logic: the six-case state machine
(``decide_rollover``), snapshot assembly (``build_rollover_snapshot``), and
downstream classification (``classify_rollover_outcome``). No filesystem, no
``MetaTrader5``, no real clock - every case is driven by explicit inputs."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode, MT5RolloverOutcome
from app.mt5.rollover import build_rollover_snapshot, classify_rollover_outcome, decide_rollover
from tests.mt5_rollover_support import NOW, UTC_POLICY, default_rollover_state

TODAY_KEY = "2026-01-01"
YESTERDAY_KEY = "2025-12-31"
TOMORROW_KEY = "2026-01-02"


# --- Case: absent persistence -> MIDDAY_BOOTSTRAP ---


def test_absent_persistence_bootstraps_midday() -> None:
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="ABSENT",
        persisted_state=None,
    )
    assert outcome is MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY
    assert state is not None
    assert state.establishment_mode is MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP
    assert state.rollover_equity == Decimal("50000")
    assert state.trading_day_key == TODAY_KEY
    assert state.rollover_timezone == UTC_POLICY.rollover_timezone
    assert state.rollover_hour == UTC_POLICY.rollover_hour


def test_bootstrap_never_reported_as_plain_ready() -> None:
    outcome, _ = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="ABSENT",
        persisted_state=None,
    )
    assert outcome is not MT5RolloverOutcome.READY


# --- Case: persistence unavailable/corrupt -> fail closed ---


def test_persistence_corrupt_fails_closed() -> None:
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="CORRUPT",
        persisted_state=None,
    )
    assert outcome is MT5RolloverOutcome.PERSISTENCE_CORRUPT
    assert state is None


def test_persistence_unavailable_fails_closed() -> None:
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="UNAVAILABLE",
        persisted_state=None,
    )
    assert outcome is MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE
    assert state is None


# --- Case: same-day reuse ---


def test_same_day_reuses_persisted_equity_exactly() -> None:
    persisted = default_rollover_state(
        trading_day_key=TODAY_KEY, rollover_equity=Decimal("98765.43"), establishment_mode=MT5RolloverEstablishmentMode.SAME_DAY_REUSE
    )
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),  # deliberately different from persisted equity
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.READY
    assert state == persisted
    assert state.rollover_equity == Decimal("98765.43")


def test_intraday_equity_change_does_not_alter_rollover() -> None:
    persisted = default_rollover_state(trading_day_key=TODAY_KEY, rollover_equity=Decimal("100000"))
    for intraday_equity in (Decimal("50000"), Decimal("150000"), Decimal("100000.01")):
        _, state = decide_rollover(
            current_trading_day_key=TODAY_KEY,
            current_equity=intraday_equity,
            as_of=NOW,
            policy=UTC_POLICY,
            persisted_read_status="VALID",
            persisted_state=persisted,
        )
        assert state is not None
        assert state.rollover_equity == Decimal("100000")


def test_same_day_reuse_does_not_rewrite_state_object() -> None:
    persisted = default_rollover_state(trading_day_key=TODAY_KEY)
    _, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("999999"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert state is persisted  # identical object, not a rebuilt copy


# --- Case: same-day config mismatch ---


def test_same_day_timezone_mismatch_fails_closed() -> None:
    persisted = default_rollover_state(trading_day_key=TODAY_KEY, rollover_timezone="America/New_York")
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.CONFIG_MISMATCH
    assert state is None


def test_same_day_hour_mismatch_fails_closed() -> None:
    persisted = default_rollover_state(trading_day_key=TODAY_KEY, rollover_hour=5)
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.CONFIG_MISMATCH
    assert state is None


# --- Case: new-day transition ---


def test_new_day_establishes_fresh_state_from_current_equity() -> None:
    persisted = default_rollover_state(trading_day_key=YESTERDAY_KEY, rollover_equity=Decimal("100000"))
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("103500"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.READY
    assert state is not None
    assert state.rollover_equity == Decimal("103500")
    assert state.trading_day_key == TODAY_KEY
    assert state.establishment_mode is MT5RolloverEstablishmentMode.POST_BOUNDARY_FIRST_OBSERVATION


def test_new_day_config_change_is_allowed_and_persisted_under_new_config() -> None:
    """A timezone/hour change across a trading-day transition must NOT
    trigger CONFIG_MISMATCH - the new state simply adopts the current
    policy."""
    persisted = default_rollover_state(
        trading_day_key=YESTERDAY_KEY, rollover_timezone="America/New_York", rollover_hour=5
    )
    changed_policy = UTC_POLICY  # UTC/0, deliberately different from the persisted timezone/hour
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("100000"),
        as_of=NOW,
        policy=changed_policy,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.READY
    assert state is not None
    assert state.rollover_timezone == "UTC"
    assert state.rollover_hour == 0
    assert state.establishment_mode is MT5RolloverEstablishmentMode.POST_BOUNDARY_FIRST_OBSERVATION


# --- Case: future state ---


def test_future_persisted_day_fails_closed() -> None:
    persisted = default_rollover_state(trading_day_key=TOMORROW_KEY)
    outcome, state = decide_rollover(
        current_trading_day_key=TODAY_KEY,
        current_equity=Decimal("50000"),
        as_of=NOW,
        policy=UTC_POLICY,
        persisted_read_status="VALID",
        persisted_state=persisted,
    )
    assert outcome is MT5RolloverOutcome.FUTURE_STATE
    assert state is None


# --- Precondition guard ---


def test_valid_status_without_state_raises_assertion() -> None:
    with pytest.raises(AssertionError):
        decide_rollover(
            current_trading_day_key=TODAY_KEY,
            current_equity=Decimal("50000"),
            as_of=NOW,
            policy=UTC_POLICY,
            persisted_read_status="VALID",
            persisted_state=None,
        )


# --- build_rollover_snapshot / classify_rollover_outcome ---


def test_build_rollover_snapshot_assembles_usable_result() -> None:
    state = default_rollover_state(establishment_mode=MT5RolloverEstablishmentMode.SAME_DAY_REUSE)
    snapshot = build_rollover_snapshot(
        as_of=NOW,
        current_equity=Decimal("101000"),
        floating_pnl=Decimal("-42.50"),
        outcome=MT5RolloverOutcome.READY,
        rollover_state=state,
    )
    assert snapshot.rollover_outcome is MT5RolloverOutcome.READY
    assert snapshot.rollover_state == state
    assert snapshot.current_equity == Decimal("101000")
    assert snapshot.floating_pnl == Decimal("-42.50")


def test_build_rollover_snapshot_assembles_blocking_result() -> None:
    snapshot = build_rollover_snapshot(
        as_of=NOW,
        current_equity=Decimal("101000"),
        floating_pnl=Decimal("0"),
        outcome=MT5RolloverOutcome.CONFIG_MISMATCH,
        rollover_state=None,
    )
    assert snapshot.rollover_outcome is MT5RolloverOutcome.CONFIG_MISMATCH
    assert snapshot.rollover_state is None


@pytest.mark.parametrize(
    "outcome",
    [MT5RolloverOutcome.READY, MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY],
)
def test_classify_usable_outcomes(outcome: MT5RolloverOutcome) -> None:
    assert classify_rollover_outcome(outcome) == "USABLE_FOR_FUTURE_ACCOUNT_RISK_ASSEMBLY"


@pytest.mark.parametrize(
    "outcome",
    [
        MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE,
        MT5RolloverOutcome.PERSISTENCE_CORRUPT,
        MT5RolloverOutcome.CONFIG_MISMATCH,
        MT5RolloverOutcome.FUTURE_STATE,
    ],
)
def test_classify_blocking_outcomes(outcome: MT5RolloverOutcome) -> None:
    assert classify_rollover_outcome(outcome) == "BLOCK_RUNTIME_CYCLE"


def test_decide_rollover_does_not_construct_account_risk_snapshot() -> None:
    import app.mt5.rollover as rollover_module

    assert "AccountRiskSnapshot" not in rollover_module.__dict__


def test_rollover_module_never_invokes_risk_gate() -> None:
    import ast
    import inspect

    import app.mt5.rollover as rollover_module

    tree = ast.parse(inspect.getsource(rollover_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    offending = {name for name in names if name == "app.risk" or name.startswith("app.risk.")}
    assert not offending
    assert "RiskGate" not in rollover_module.__dict__
