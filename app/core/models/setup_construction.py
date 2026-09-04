"""Setup Construction output contracts.

Aggregates one already-produced ``StrategyPolicyResult`` into a per-Policy-
eligible-``StrategyFamily`` price/risk setup verdict: the concrete
entry/reference price, protective ``stop_loss`` and ``risk_per_unit`` a
directional family needs before it can obtain a Stage 7 ``CandidateRiskInput``.
Deliberately narrower than ``TradeSetup`` (never reused - see the approved
Setup Construction design): carries no ``confidence``, no ``entry_zone``, no
``risk_reward``, since nothing upstream of this model produces any of those
facts in V1.

The embedded ``StrategyPolicyResult`` (and, through it, the whole Stage
5/6 chain) is carried unchanged: no evidence, direction, or upstream fact is
ever copied out of it - every ``SetupConstructionResult`` back-references its
family only. ``CandidateTradeSetup`` never duplicates ``PositionRecord``'s or
``MT5BrokerSizingRequest``'s own fields beyond what both genuinely need as a
caller-supplied fact; those two remain the sole downstream sizing/tracking
authorities.

``SetupConstructionOutcome.CONSTRUCTED`` means only that a concrete,
geometrically valid price/risk setup was derived - never that a trade,
position, or execution of any kind has been approved. Setup Construction
never decides LONG vs SHORT (Judge's exclusive authority), never ranks or
reconciles simultaneously eligible families, never allocates monetary risk
(Stage 7/8/9's exclusive authority), and never sizes broker volume (Stage
10C's exclusive authority).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import model_validator

from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.policy_gate_result import StrategyPolicyResult


class CandidateTradeSetup(DomainModel):
    """One Policy-eligible family's concrete, geometrically valid price/risk
    setup.

    ``direction`` is always ``LONG`` or ``SHORT`` - the two-directional
    mapping of Judge's own ``DirectionalCandidate``, never ``NEUTRAL``/
    ``WAIT``. ``take_profit_levels`` is always empty in V1 - no deterministic
    risk/reward target rule is approved. ``risk_per_unit`` is deliberately
    unconstrained (mirrors ``CandidateRiskInput.risk_per_unit`` exactly): its
    sole consumer is the Stage 7 compatibility bridge (see
    ``app.decision.setup_construction.to_candidate_risk_inputs``), which
    never constructs this model with a non-positive value in the first place
    - construction-time validation stays a defensive backstop, not the
    primary business-rule enforcement point.
    """

    family: StrategyFamily
    direction: TradeDirection
    symbol: Symbol
    entry_price: Price
    stop_loss: Price
    take_profit_levels: tuple[Price, ...] = ()
    risk_per_unit: Decimal
    signal_time: Timestamp
    valid_until: Timestamp

    @model_validator(mode="after")
    def _validate_direction_is_actionable(self) -> Self:
        if self.direction not in (TradeDirection.LONG, TradeDirection.SHORT):
            raise ValueError("CandidateTradeSetup requires LONG or SHORT direction")
        return self

    @model_validator(mode="after")
    def _validate_stop_side(self) -> Self:
        valid = self.stop_loss < self.entry_price if self.direction is TradeDirection.LONG else self.stop_loss > self.entry_price
        if not valid:
            raise ValueError("stop_loss is on the wrong side of entry_price for direction")
        return self

    @model_validator(mode="after")
    def _validate_timeline(self) -> Self:
        if self.valid_until <= self.signal_time:
            raise ValueError("valid_until must be after signal_time")
        return self


class SetupConstructionResult(DomainModel):
    """One Policy-eligible family's Setup Construction verdict.

    ``reasons`` is empty if and only if ``outcome`` is ``CONSTRUCTED``; when
    non-empty it carries exactly one canonical reason - every check Setup
    Construction performs is sequential/short-circuiting, so no combination
    of simultaneous reasons is ever representable, mirroring
    ``PortfolioFamilyResult``/``SessionFamilyResult``'s own "at most one
    reason" discipline rather than ``RiskFamilyResult``'s multi-reason one.
    """

    family: StrategyFamily
    outcome: SetupConstructionOutcome
    setup: CandidateTradeSetup | None = None
    reasons: tuple[SetupBlockReason, ...] = ()

    @model_validator(mode="after")
    def _validate_setup_presence(self) -> Self:
        if self.outcome is SetupConstructionOutcome.CONSTRUCTED:
            if self.setup is None:
                raise ValueError("CONSTRUCTED requires setup")
            if self.reasons:
                raise ValueError("CONSTRUCTED must not carry reasons")
        else:
            if self.setup is not None:
                raise ValueError("BLOCKED must not carry setup")
            if len(self.reasons) != 1:
                raise ValueError("BLOCKED requires exactly one reason")
        return self

    @model_validator(mode="after")
    def _validate_setup_family_matches(self) -> Self:
        if self.setup is not None and self.setup.family is not self.family:
            raise ValueError("setup.family must equal the enclosing result's family")
        return self


class StrategySetupResult(DomainModel):
    """Deterministic Setup Construction aggregation: one setup verdict per
    Policy-``ELIGIBLE_FOR_RISK_REVIEW`` family, in canonical order.

    A Policy-``BLOCKED`` family never receives a ``SetupConstructionResult``
    at all - that path is already fully handled inside ``RiskGate`` itself
    (``RiskBlockReason.POLICY_NOT_ELIGIBLE``) without any Setup Construction
    involvement.
    """

    strategy_policy_result: StrategyPolicyResult
    family_results: tuple[SetupConstructionResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_policy_eligible_families(self) -> Self:
        expected = tuple(
            result.family
            for result in self.strategy_policy_result.family_results
            if result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
        )
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly the Policy-eligible families, in canonical order")
        return self


__all__ = ["CandidateTradeSetup", "SetupConstructionResult", "StrategySetupResult"]
