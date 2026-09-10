"""Pre-commit corrective review tests: ``is_issuable`` must require
``tracking_persisted is True`` in addition to ``tracking_creation_outcome ==
CREATED`` - a CREATED-but-not-persisted recommendation must never be exposed
as operator-facing output, and its cause must be a typed
``IssuanceFailureReason``, never the misleading ``CREATED`` outcome itself.
A provenance-only failure (tracking persisted, provenance not) MAY remain
exposed, but must stay visible in ``OperationalDiagnosticsDTO.
issuance_persistence`` and the cycle must report ``DEGRADED``, never
``READY``."""

from __future__ import annotations

from app.application.advisory_service import is_issuable, map_advisory_response, map_operational_diagnostics
from app.application.dto import ApplicationAdvisoryStatus, IssuanceFailureReason, NoTradeStage
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from tests.application_support import (
    netting_guard,
    one_family_actionable_others_ineligible,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)

FAMILY = StrategyFamily.TREND_FOLLOWING
TRADE_ID = "cyc__TREND_FOLLOWING"


def _cycle_for(*, tracking_persisted: bool, provenance_persisted: bool, runtime_outcome=RuntimeCycleOutcome.READY):
    drp, frcr = one_family_actionable_others_ineligible(FAMILY, TRADE_ID)
    outcome = tracking_outcome(TRADE_ID, MT5TrackedRecommendationCreationOutcome.CREATED)
    # tracking_outcome() always ties tracking_persisted/provenance_persisted
    # to CREATED together - override explicitly here for the exact
    # persistence combination each test needs.
    outcome = outcome.model_copy(update={"tracking_persisted": tracking_persisted, "provenance_persisted": provenance_persisted})
    rcr = runtime_cycle_result(
        outcome=runtime_outcome,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=(outcome,),
    )
    return production_advisory_cycle_result(rcr=rcr)


# --- is_issuable direct checks ----------------------------------------------


def test_is_issuable_requires_tracking_persisted_true() -> None:
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        new_tracking_persistence_outcomes=(
            tracking_outcome(TRADE_ID, MT5TrackedRecommendationCreationOutcome.CREATED).model_copy(
                update={"tracking_persisted": False, "provenance_persisted": True}
            ),
        ),
    )
    assert is_issuable(TRADE_ID, rcr) is False


def test_is_issuable_true_when_created_and_persisted_and_provenance_persisted() -> None:
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        new_tracking_persistence_outcomes=(tracking_outcome(TRADE_ID, MT5TrackedRecommendationCreationOutcome.CREATED),),
    )
    assert is_issuable(TRADE_ID, rcr) is True


def test_is_issuable_true_when_created_and_persisted_but_provenance_not_persisted() -> None:
    """Provenance gating is NOT part of is_issuable - see section 4 of the
    pre-commit review."""
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        new_tracking_persistence_outcomes=(
            tracking_outcome(TRADE_ID, MT5TrackedRecommendationCreationOutcome.CREATED).model_copy(
                update={"tracking_persisted": True, "provenance_persisted": False}
            ),
        ),
    )
    assert is_issuable(TRADE_ID, rcr) is True


# --- full end-to-end scenarios via map_advisory_response --------------------


def test_created_persisted_true_provenance_true_exposed() -> None:
    cycle = _cycle_for(tracking_persisted=True, provenance_persisted=True)
    response = map_advisory_response("cyc", cycle)
    assert len(response.recommendations) == 1
    assert response.recommendations[0].trade_id == TRADE_ID
    assert FAMILY not in {r.strategy_family for r in response.no_trade_reasons}


def test_created_persisted_false_provenance_true_not_exposed() -> None:
    cycle = _cycle_for(tracking_persisted=False, provenance_persisted=True)
    response = map_advisory_response("cyc", cycle)
    assert response.recommendations == ()
    matching = [r for r in response.no_trade_reasons if r.strategy_family is FAMILY]
    assert len(matching) == 1
    assert matching[0].stage is NoTradeStage.ISSUANCE
    assert matching[0].codes == (IssuanceFailureReason.TRACKING_PERSISTENCE_FAILED,)
    # never represented via the misleading CREATED outcome itself
    assert MT5TrackedRecommendationCreationOutcome.CREATED not in matching[0].codes


def test_created_persisted_false_provenance_false_not_exposed() -> None:
    cycle = _cycle_for(tracking_persisted=False, provenance_persisted=False)
    response = map_advisory_response("cyc", cycle)
    assert response.recommendations == ()
    matching = [r for r in response.no_trade_reasons if r.strategy_family is FAMILY]
    assert matching[0].codes == (IssuanceFailureReason.TRACKING_PERSISTENCE_FAILED,)


def test_snapshot_unavailable_not_exposed_with_correct_typed_cause() -> None:
    drp, frcr = one_family_actionable_others_ineligible(FAMILY, TRADE_ID)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.ALLOWED),
        new_tracking_persistence_outcomes=(tracking_outcome(TRADE_ID, MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE),),
    )
    cycle = production_advisory_cycle_result(rcr=rcr)
    response = map_advisory_response("cyc", cycle)
    assert response.recommendations == ()
    matching = [r for r in response.no_trade_reasons if r.strategy_family is FAMILY]
    assert matching[0].codes == (MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE,)


# --- provenance-failure policy (section 4) ----------------------------------


def test_provenance_failure_alone_keeps_recommendation_but_status_degraded() -> None:
    """CREATED + tracking_persisted=True + provenance_persisted=False:
    the recommendation MAY remain exposed, but the cycle-wide status must be
    DEGRADED (RuntimeCycleOutcome already degrades on any provenance write
    failure - app.orchestration.runtime_cycle._compute_cycle_outcome's own
    any_provenance_write_failure input), and the failure must be visible in
    OperationalDiagnosticsDTO.issuance_persistence - never silently hidden."""
    cycle = _cycle_for(tracking_persisted=True, provenance_persisted=False, runtime_outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED)
    response = map_advisory_response("cyc", cycle)

    assert len(response.recommendations) == 1
    assert response.recommendations[0].trade_id == TRADE_ID
    assert response.status is ApplicationAdvisoryStatus.DEGRADED  # never READY despite a recommendation present

    diagnostics = map_operational_diagnostics(cycle)
    matching = [entry for entry in diagnostics.issuance_persistence if entry.trade_id == TRADE_ID]
    assert len(matching) == 1
    assert matching[0].tracking_persisted is True
    assert matching[0].provenance_persisted is False


def test_issuance_persistence_diagnostic_is_verbatim_copy() -> None:
    cycle = _cycle_for(tracking_persisted=True, provenance_persisted=True)
    diagnostics = map_operational_diagnostics(cycle)
    assert len(diagnostics.issuance_persistence) == 1
    entry = diagnostics.issuance_persistence[0]
    assert entry.trade_id == TRADE_ID
    assert entry.tracking_creation_outcome is MT5TrackedRecommendationCreationOutcome.CREATED
    assert entry.tracking_persisted is True
    assert entry.provenance_persisted is True
