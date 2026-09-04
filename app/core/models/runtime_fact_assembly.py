"""Runtime Fact Assembly output contract.

Assembles one Stage 7 ``AccountRiskSnapshot`` from three already-produced
Stage 10B/10C/10D assessments (``MT5RolloverSnapshot``,
``MT5RealizedDailyPnLAssessment``, ``MT5OpenRiskAssessment``) - never a
duplicate account-risk model, never a new financial computation. Every
``AccountRiskSnapshot`` field is either a direct, unchanged copy of an
upstream field or is absent entirely (``READY`` requires all three upstream
assessments simultaneously usable and mutually timestamp-coherent).

The three upstream assessments are carried unchanged on
``AccountRiskSnapshotAssembly`` regardless of ``outcome`` - mirroring every
Stage 5-10 result model's own "embed the input unchanged, never copy a fact
out in isolation" discipline - so a ``BLOCKED`` assembly's detailed root
cause remains fully inspectable (via each assessment's own ``outcome``/
``blocked_reasons``/``unsafe_tickets``/``unsafe_deal_tickets``) without
duplicating any of that detail into a new, parallel reason taxonomy.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason, RuntimeFactAssemblyOutcome
from app.core.models.base import DomainModel, Timestamp
from app.core.models.mt5_history import MT5RealizedDailyPnLAssessment
from app.core.models.mt5_position import MT5OpenRiskAssessment
from app.core.models.mt5_rollover import MT5RolloverSnapshot
from app.core.models.risk_gate_result import AccountRiskSnapshot

_REASON_ORDER: tuple[RuntimeFactAssemblyBlockReason, ...] = tuple(RuntimeFactAssemblyBlockReason)


class AccountRiskSnapshotAssembly(DomainModel):
    """One deterministic ``AccountRiskSnapshot`` assembly attempt.

    ``account_snapshot`` is present if and only if ``outcome`` is ``READY``.
    ``reasons`` is empty if and only if ``outcome`` is ``READY``; when
    non-empty it is canonically ordered (``RuntimeFactAssemblyBlockReason``
    declaration order) and duplicate-free - multiple simultaneous upstream
    failures accumulate rather than hiding behind a single precedence
    winner, mirroring ``MT5OpenRiskAssessment.blocked_reasons``/
    ``RiskFamilyResult.reasons``'s own accumulation discipline.
    """

    as_of: Timestamp
    outcome: RuntimeFactAssemblyOutcome
    account_snapshot: AccountRiskSnapshot | None = None
    rollover_snapshot: MT5RolloverSnapshot
    realized_daily_pnl_assessment: MT5RealizedDailyPnLAssessment
    open_risk_assessment: MT5OpenRiskAssessment
    reasons: tuple[RuntimeFactAssemblyBlockReason, ...] = ()

    @model_validator(mode="after")
    def _validate_snapshot_presence(self) -> Self:
        if self.outcome is RuntimeFactAssemblyOutcome.READY:
            if self.account_snapshot is None:
                raise ValueError("READY requires account_snapshot")
            if self.reasons:
                raise ValueError("READY must not carry reasons")
        else:
            if self.account_snapshot is not None:
                raise ValueError("BLOCKED must not carry account_snapshot")
            if not self.reasons:
                raise ValueError("BLOCKED requires at least one reason")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.reasons]
        if indexes != sorted(indexes):
            raise ValueError("reasons must be in canonical RuntimeFactAssemblyBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("reasons must not contain duplicates")
        return self


__all__ = ["AccountRiskSnapshotAssembly"]
