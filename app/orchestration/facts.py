"""Runtime Fact Assembly (Final Runtime Integration, Part B).

Assembles one Stage 7 ``AccountRiskSnapshot`` from three already-produced
Stage 10B/10C/10D assessments. Never invokes ``MT5Client``, rollover/
recommendation persistence, ``app.mt5.risk``/``app.mt5.history`` (the
assessments themselves are already computed), RiskGate/PortfolioSupervisor/
SessionGate/SetupConstruction/StatisticsAggregator, and never reads the
filesystem or the wall clock - a pure, synchronous, stateless function of its
four explicit inputs.

Reads only each upstream assessment's own ``outcome``/``rollover_outcome``
and the specific fields ``AccountRiskSnapshot`` needs - never recomputes
rollover equity, realized PnL, or open risk from any more primitive fact
(positions, deals, account equity); Stage 10B/10C/10D remain the sole
authorities for those figures. Whether the three assessments are jointly
usable and mutually timestamp-coherent is exactly the information this
module is allowed to act on.

``as_of`` is always caller-supplied: the intended calling convention is that
a future runtime orchestrator captures exactly one ``cycle_as_of`` and
supplies it, unchanged, as the ``as_of`` argument to
``build_rollover_snapshot``/``assess_open_risk``/``compute_realized_daily_pnl``
*and* to this module's own ``as_of`` parameter - so every upstream
assessment's own ``as_of`` field is expected to already equal this module's
``as_of`` by construction, not by a permitted tolerance. A mismatch is
treated as a genuine coherence defect (a stale or wrongly-paired assessment
object), never silently accepted.
"""

from __future__ import annotations

from app.core.enums.mt5_history import MT5RealizedPnLOutcome
from app.core.enums.mt5_position import MT5OpenRiskOutcome
from app.core.enums.mt5_rollover import MT5RolloverOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason, RuntimeFactAssemblyOutcome
from app.core.models.base import Timestamp
from app.core.models.mt5_history import MT5RealizedDailyPnLAssessment
from app.core.models.mt5_position import MT5OpenRiskAssessment
from app.core.models.mt5_rollover import MT5RolloverSnapshot
from app.core.models.risk_gate_result import AccountRiskSnapshot
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly

_USABLE_ROLLOVER_OUTCOMES: frozenset[MT5RolloverOutcome] = frozenset(
    {MT5RolloverOutcome.READY, MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY}
)
"""A locally-owned copy of the usable-outcome set - not imported from
``app.core.models.mt5_rollover`` or ``app.mt5.rollover`` (each of which
already maintains its own independent copy of this identical membership to
self-validate/classify), mirroring the Stage 5A/6A/6C/7/8/9/10B/10C/10D
precedent of the operational component and the result model's self-
validation maintaining independent copies of the same primitive rather than
cross-importing one from the other."""

_REASON_ORDER: tuple[RuntimeFactAssemblyBlockReason, ...] = tuple(RuntimeFactAssemblyBlockReason)


def _timestamps_coherent(
    *,
    as_of: Timestamp,
    rollover_snapshot: MT5RolloverSnapshot,
    realized_daily_pnl_assessment: MT5RealizedDailyPnLAssessment,
    open_risk_assessment: MT5OpenRiskAssessment,
) -> bool:
    """Every upstream assessment's own ``as_of`` must exactly equal the
    caller-supplied ``as_of`` - all three are themselves caller-supplied
    arguments to their own Stage 10B/10C/10D pure functions (never self-
    stamped from an internal wall clock), so exact equality is both
    achievable and appropriate to enforce, never a tolerance. When rollover
    usably carries a ``trading_day_key`` (see ``_rollover_usable``), it must
    also agree with the realized-PnL assessment's own ``trading_day_key`` -
    both describe "which broker trading day this financial state belongs
    to"; a disagreement here is the same class of coherence defect as an
    ``as_of`` mismatch, not a distinct one."""
    if rollover_snapshot.as_of != as_of:
        return False
    if realized_daily_pnl_assessment.as_of != as_of:
        return False
    if open_risk_assessment.as_of != as_of:
        return False
    if rollover_snapshot.rollover_state is not None:
        if rollover_snapshot.rollover_state.trading_day_key != realized_daily_pnl_assessment.trading_day_key:
            return False
    return True


def assemble_account_risk_snapshot(
    *,
    as_of: Timestamp,
    rollover_snapshot: MT5RolloverSnapshot,
    realized_daily_pnl_assessment: MT5RealizedDailyPnLAssessment,
    open_risk_assessment: MT5OpenRiskAssessment,
) -> AccountRiskSnapshotAssembly:
    """The full Runtime Fact Assembly attempt: ``READY`` only if every
    upstream assessment is simultaneously usable and mutually timestamp-
    coherent - no partial/best-effort ``AccountRiskSnapshot`` is ever
    produced, and every legitimate failure category accumulates into
    ``reasons`` rather than hiding behind a single precedence winner."""
    reason_set: set[RuntimeFactAssemblyBlockReason] = set()

    rollover_usable = rollover_snapshot.rollover_outcome in _USABLE_ROLLOVER_OUTCOMES
    if not rollover_usable:
        reason_set.add(RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE)

    realized_pnl_usable = realized_daily_pnl_assessment.outcome is MT5RealizedPnLOutcome.READY
    if not realized_pnl_usable:
        reason_set.add(RuntimeFactAssemblyBlockReason.REALIZED_PNL_UNAVAILABLE)

    open_risk_usable = open_risk_assessment.outcome is MT5OpenRiskOutcome.READY
    if not open_risk_usable:
        reason_set.add(RuntimeFactAssemblyBlockReason.OPEN_RISK_UNAVAILABLE)

    if not _timestamps_coherent(
        as_of=as_of,
        rollover_snapshot=rollover_snapshot,
        realized_daily_pnl_assessment=realized_daily_pnl_assessment,
        open_risk_assessment=open_risk_assessment,
    ):
        reason_set.add(RuntimeFactAssemblyBlockReason.TIMESTAMP_MISMATCH)

    if reason_set:
        reasons = tuple(reason for reason in _REASON_ORDER if reason in reason_set)
        return AccountRiskSnapshotAssembly(
            as_of=as_of,
            outcome=RuntimeFactAssemblyOutcome.BLOCKED,
            rollover_snapshot=rollover_snapshot,
            realized_daily_pnl_assessment=realized_daily_pnl_assessment,
            open_risk_assessment=open_risk_assessment,
            reasons=reasons,
        )

    assert rollover_snapshot.rollover_state is not None  # guaranteed by rollover_usable
    assert realized_daily_pnl_assessment.realized_daily_pnl is not None  # guaranteed by realized_pnl_usable
    assert open_risk_assessment.current_open_risk_to_stop is not None  # guaranteed by open_risk_usable

    account_snapshot = AccountRiskSnapshot(
        as_of=as_of,
        rollover_equity=rollover_snapshot.rollover_state.rollover_equity,
        current_equity=rollover_snapshot.current_equity,
        realized_daily_pnl=realized_daily_pnl_assessment.realized_daily_pnl,
        floating_pnl=rollover_snapshot.floating_pnl,
        current_open_risk_to_stop=open_risk_assessment.current_open_risk_to_stop,
    )
    return AccountRiskSnapshotAssembly(
        as_of=as_of,
        outcome=RuntimeFactAssemblyOutcome.READY,
        account_snapshot=account_snapshot,
        rollover_snapshot=rollover_snapshot,
        realized_daily_pnl_assessment=realized_daily_pnl_assessment,
        open_risk_assessment=open_risk_assessment,
    )


__all__ = ["assemble_account_risk_snapshot"]
