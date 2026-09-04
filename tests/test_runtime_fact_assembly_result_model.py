"""``AccountRiskSnapshotAssembly`` invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason, RuntimeFactAssemblyOutcome
from app.core.models.risk_gate_result import AccountRiskSnapshot
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from tests.risk_gate_support import default_account_snapshot
from tests.runtime_fact_assembly_support import AS_OF, rollover_ready, usable_open_risk, usable_realized_pnl


def _base_fields(**overrides: object) -> dict[object, object]:
    fields: dict[object, object] = {
        "as_of": AS_OF,
        "rollover_snapshot": rollover_ready(),
        "realized_daily_pnl_assessment": usable_realized_pnl(),
        "open_risk_assessment": usable_open_risk(),
    }
    fields.update(overrides)
    return fields


def test_ready_requires_snapshot_present() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(**_base_fields(outcome=RuntimeFactAssemblyOutcome.READY, account_snapshot=None))


def test_ready_with_snapshot_constructs() -> None:
    assembly = AccountRiskSnapshotAssembly(
        **_base_fields(outcome=RuntimeFactAssemblyOutcome.READY, account_snapshot=default_account_snapshot())
    )
    assert assembly.outcome is RuntimeFactAssemblyOutcome.READY


def test_ready_has_no_block_reasons() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(
            **_base_fields(
                outcome=RuntimeFactAssemblyOutcome.READY,
                account_snapshot=default_account_snapshot(),
                reasons=(RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE,),
            )
        )


def test_blocked_requires_snapshot_absent() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(
            **_base_fields(
                outcome=RuntimeFactAssemblyOutcome.BLOCKED,
                account_snapshot=default_account_snapshot(),
                reasons=(RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE,),
            )
        )


def test_blocked_requires_at_least_one_reason() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(**_base_fields(outcome=RuntimeFactAssemblyOutcome.BLOCKED, reasons=()))


def test_blocked_with_reason_constructs() -> None:
    assembly = AccountRiskSnapshotAssembly(
        **_base_fields(outcome=RuntimeFactAssemblyOutcome.BLOCKED, reasons=(RuntimeFactAssemblyBlockReason.OPEN_RISK_UNAVAILABLE,))
    )
    assert assembly.account_snapshot is None


def test_reasons_must_be_canonically_ordered() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(
            **_base_fields(
                outcome=RuntimeFactAssemblyOutcome.BLOCKED,
                reasons=(RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH, RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE),
            )
        )


def test_reasons_must_not_contain_duplicates() -> None:
    with pytest.raises(ValidationError):
        AccountRiskSnapshotAssembly(
            **_base_fields(
                outcome=RuntimeFactAssemblyOutcome.BLOCKED,
                reasons=(RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE, RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE),
            )
        )


def test_upstream_assessments_are_retained_on_blocked_for_audit() -> None:
    rollover = rollover_ready()
    pnl = usable_realized_pnl()
    risk = usable_open_risk()
    assembly = AccountRiskSnapshotAssembly(
        as_of=AS_OF,
        outcome=RuntimeFactAssemblyOutcome.BLOCKED,
        rollover_snapshot=rollover,
        realized_daily_pnl_assessment=pnl,
        open_risk_assessment=risk,
        reasons=(RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH,),
    )
    # The detailed upstream facts remain fully inspectable without a
    # duplicated reason taxonomy - mirrors every Stage 5-10 embed-unchanged
    # precedent.
    assert assembly.rollover_snapshot is rollover
    assert assembly.realized_daily_pnl_assessment is pnl
    assert assembly.open_risk_assessment is risk
