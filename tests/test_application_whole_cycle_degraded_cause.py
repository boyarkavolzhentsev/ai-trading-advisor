"""Pre-commit corrective review tests: a whole-cycle "Risk onward never ran"
condition (``RuntimeCycleResult.decision_risk_pipeline_result`` absent
entirely, or present with ``DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK``)
must never be represented as a fabricated per-family
``NoTradeReasonDTO`` - it must instead be explained via
``TradingDataQualityDTO.account_risk_snapshot_ready``/
``account_risk_snapshot_block_reasons``, using only facts already present on
``RuntimeCycleResult``. Also reconfirms the ``SERVICE_UNAVAILABLE``
early-return shape stays safe with the new DTO fields."""

from __future__ import annotations

from app.application.advisory_service import derive_no_trade_reason, map_advisory_response, map_trading_data_quality
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason, RuntimeFactAssemblyOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.application_support import (
    AS_OF,
    decision_risk_pipeline_result,
    eligibility_entry,
    judge_result,
    policy_family_result,
    policy_result,
    production_advisory_cycle_result,
    router_result,
    runtime_cycle_result,
    setup_family_result,
    setup_result,
)

FAMILY = StrategyFamily.MEAN_REVERSION


def _pipeline_up_to_setup():
    router = router_result((eligibility_entry(FAMILY),))
    judge = judge_result(router)
    pol = policy_result(judge, (policy_family_result(FAMILY),))
    setup = setup_result(pol, (setup_family_result(FAMILY),))
    return setup


def test_assembly_never_attempted_yields_no_per_family_reason_but_diagnostic_explains_it() -> None:
    """account_risk_snapshot_assembly is None entirely (Runtime Fact
    Assembly was never even attempted this cycle, e.g. positions/history
    reads did not both confirm OK) - never fabricated as a per-family
    reason."""
    setup = _pipeline_up_to_setup()
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED,
        decision_risk_pipeline_result=drp,
        positions_read_status="UNAVAILABLE",
        history_read_status="OK",
    )
    assert derive_no_trade_reason(FAMILY, rcr) is None

    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    data_quality = map_trading_data_quality(cycle)
    assert data_quality.account_risk_snapshot_ready is False
    assert data_quality.account_risk_snapshot_block_reasons == ()  # never attempted, not "blocked"
    assert data_quality.positions_read_status == "UNAVAILABLE"  # the real, typed, raw cause remains visible
    assert data_quality.runtime_outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED


def test_assembly_attempted_and_blocked_surfaces_its_own_typed_reasons() -> None:
    """account_risk_snapshot_assembly was actually attempted (all three
    Stage 10B/10C/10D sub-assessments were computed) but itself came back
    BLOCKED - its own typed reasons must be surfaced, not swallowed."""
    setup = _pipeline_up_to_setup()
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    assembly = AccountRiskSnapshotAssembly.model_construct(
        as_of=AS_OF,
        outcome=RuntimeFactAssemblyOutcome.BLOCKED,
        account_snapshot=None,
        rollover_snapshot=None,
        realized_daily_pnl_assessment=None,
        open_risk_assessment=None,
        reasons=(RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE,),
    )
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED, decision_risk_pipeline_result=drp, positions_read_status="OK", history_read_status="OK")
    rcr = rcr.model_copy(update={"account_risk_snapshot_assembly": assembly})

    assert derive_no_trade_reason(FAMILY, rcr) is None  # still never a fabricated per-family reason

    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    data_quality = map_trading_data_quality(cycle)
    assert data_quality.account_risk_snapshot_ready is False
    assert data_quality.account_risk_snapshot_block_reasons == (RuntimeFactAssemblyBlockReason.ROLLOVER_UNAVAILABLE,)


def test_assembly_ready_reports_true() -> None:
    setup = _pipeline_up_to_setup()
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    assembly = AccountRiskSnapshotAssembly.model_construct(
        as_of=AS_OF,
        outcome=RuntimeFactAssemblyOutcome.READY,
        account_snapshot=object(),
        rollover_snapshot=None,
        realized_daily_pnl_assessment=None,
        open_risk_assessment=None,
        reasons=(),
    )
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.READY, decision_risk_pipeline_result=drp)
    rcr = rcr.model_copy(update={"account_risk_snapshot_assembly": assembly})
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    data_quality = map_trading_data_quality(cycle)
    assert data_quality.account_risk_snapshot_ready is True
    assert data_quality.account_risk_snapshot_block_reasons == ()


def test_bare_partial_degraded_is_not_treated_as_a_root_cause_by_itself() -> None:
    """runtime_outcome alone must never be read as if it were an
    explanation - the block-reasons/read-status fields carry the real
    cause; this test just pins that runtime_outcome and the explanatory
    fields are independent, queryable facts on the same DTO."""
    setup = _pipeline_up_to_setup()
    drp = decision_risk_pipeline_result(setup=setup, event=None, session=None)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED, decision_risk_pipeline_result=drp, positions_read_status="OK", history_read_status="UNAVAILABLE"
    )
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)
    data_quality = map_trading_data_quality(cycle)
    assert data_quality.runtime_outcome is RuntimeCycleOutcome.PARTIAL_DEGRADED
    assert data_quality.history_read_status == "UNAVAILABLE"  # the actual explanatory fact, distinct from runtime_outcome


# --- SERVICE_UNAVAILABLE early-return safety (reconfirmation) ---------------


def test_service_unavailable_early_return_stays_safe_with_new_fields() -> None:
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.BLOCKED, decision_risk_pipeline_result=None, mt5_state=MT5ConnectivityState.TERMINAL_UNAVAILABLE)
    cycle = production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE)

    response = map_advisory_response("cyc", cycle)
    assert response.recommendations == ()
    assert response.no_trade_reasons == ()
    assert response.data_quality.account_risk_snapshot_ready is False
    assert response.data_quality.account_risk_snapshot_block_reasons == ()
    assert response.diagnostics.issuance_persistence == ()
