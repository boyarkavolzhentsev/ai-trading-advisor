"""Stage 10B model validation: ``MT5RolloverState``, ``MT5RolloverSnapshot`` -
frozen/extra-forbid behavior, Decimal exactness, timezone-aware timestamps,
and the exact approved establishment-mode/outcome vocabulary."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode, MT5RolloverOutcome
from app.core.models.mt5_rollover import MT5RolloverSnapshot, MT5RolloverState
from tests.mt5_rollover_support import NOW, default_rollover_state

NAIVE_NOW = datetime(2026, 1, 1, 12, 0, 0)


# --- MT5RolloverEstablishmentMode / MT5RolloverOutcome vocabulary ---


def test_establishment_mode_has_exactly_three_members() -> None:
    assert {member.value for member in MT5RolloverEstablishmentMode} == {
        "MIDDAY_BOOTSTRAP",
        "POST_BOUNDARY_FIRST_OBSERVATION",
        "SAME_DAY_REUSE",
    }


def test_establishment_mode_has_no_boundary_capture_member() -> None:
    assert "BOUNDARY_CAPTURE" not in MT5RolloverEstablishmentMode.__members__


def test_rollover_outcome_has_exactly_six_members() -> None:
    assert {member.value for member in MT5RolloverOutcome} == {
        "READY",
        "BOOTSTRAPPED_MIDDAY",
        "PERSISTENCE_UNAVAILABLE",
        "PERSISTENCE_CORRUPT",
        "CONFIG_MISMATCH",
        "FUTURE_STATE",
    }


def test_rollover_outcome_has_no_account_unavailable_member() -> None:
    assert "ACCOUNT_UNAVAILABLE" not in MT5RolloverOutcome.__members__


# --- MT5RolloverState ---


def test_rollover_state_defaults_schema_version_to_one() -> None:
    state = default_rollover_state()
    assert state.schema_version == 1


def test_rollover_state_rejects_non_positive_equity() -> None:
    with pytest.raises(ValidationError):
        default_rollover_state(rollover_equity=Decimal("0"))


def test_rollover_state_rejects_negative_equity() -> None:
    with pytest.raises(ValidationError):
        default_rollover_state(rollover_equity=Decimal("-1"))


def test_rollover_state_equity_is_decimal() -> None:
    state = default_rollover_state(rollover_equity=Decimal("98765.4321"))
    assert isinstance(state.rollover_equity, Decimal)
    assert state.rollover_equity == Decimal("98765.4321")


def test_rollover_state_rejects_naive_established_at() -> None:
    with pytest.raises(ValidationError):
        default_rollover_state(established_at=NAIVE_NOW)


def test_rollover_state_rejects_malformed_trading_day_key() -> None:
    with pytest.raises(ValidationError):
        default_rollover_state(trading_day_key="not-a-date")


def test_rollover_state_rejects_out_of_range_hour() -> None:
    with pytest.raises(ValidationError):
        default_rollover_state(rollover_hour=24)


def test_rollover_state_accepts_hour_boundaries() -> None:
    assert default_rollover_state(rollover_hour=0).rollover_hour == 0
    assert default_rollover_state(rollover_hour=23).rollover_hour == 23


def test_rollover_state_frozen() -> None:
    state = default_rollover_state()
    with pytest.raises(ValidationError):
        state.rollover_equity = Decimal("1")


def test_rollover_state_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverState(
            trading_day_key="2026-01-01",
            rollover_equity=Decimal("100000"),
            established_at=NOW,
            rollover_timezone="UTC",
            rollover_hour=0,
            establishment_mode=MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP,
            rollover_minute=0,
        )


# --- MT5RolloverSnapshot ---


def _snapshot(**overrides: object) -> MT5RolloverSnapshot:
    fields: dict[str, object] = {
        "as_of": NOW,
        "rollover_outcome": MT5RolloverOutcome.READY,
        "rollover_state": default_rollover_state(establishment_mode=MT5RolloverEstablishmentMode.SAME_DAY_REUSE),
        "current_equity": Decimal("100500"),
        "floating_pnl": Decimal("-250.75"),
    }
    fields.update(overrides)
    return MT5RolloverSnapshot(**fields)


def test_snapshot_usable_outcome_requires_rollover_state() -> None:
    with pytest.raises(ValidationError):
        _snapshot(rollover_outcome=MT5RolloverOutcome.READY, rollover_state=None)


def test_snapshot_blocking_outcome_forbids_rollover_state() -> None:
    with pytest.raises(ValidationError):
        _snapshot(rollover_outcome=MT5RolloverOutcome.PERSISTENCE_CORRUPT)


def test_snapshot_blocking_outcome_accepts_none_state() -> None:
    snapshot = _snapshot(rollover_outcome=MT5RolloverOutcome.FUTURE_STATE, rollover_state=None)
    assert snapshot.rollover_state is None


def test_snapshot_bootstrapped_midday_requires_state() -> None:
    snapshot = _snapshot(
        rollover_outcome=MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY,
        rollover_state=default_rollover_state(establishment_mode=MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP),
    )
    assert snapshot.rollover_outcome is MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY


def test_snapshot_current_equity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _snapshot(current_equity=Decimal("0"))


def test_snapshot_floating_pnl_supports_negative_value() -> None:
    snapshot = _snapshot(floating_pnl=Decimal("-999.99"))
    assert snapshot.floating_pnl == Decimal("-999.99")


def test_snapshot_floating_pnl_supports_positive_value() -> None:
    snapshot = _snapshot(floating_pnl=Decimal("999.99"))
    assert snapshot.floating_pnl == Decimal("999.99")


def test_snapshot_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError):
        _snapshot(as_of=NAIVE_NOW)


def test_snapshot_frozen() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValidationError):
        snapshot.current_equity = Decimal("1")


def test_snapshot_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        _snapshot(currency="USD")


def test_snapshot_has_no_realized_daily_pnl_field() -> None:
    assert "realized_daily_pnl" not in MT5RolloverSnapshot.model_fields


def test_snapshot_has_no_current_open_risk_to_stop_field() -> None:
    assert "current_open_risk_to_stop" not in MT5RolloverSnapshot.model_fields


def test_snapshot_has_no_currency_field() -> None:
    assert "currency" not in MT5RolloverSnapshot.model_fields
