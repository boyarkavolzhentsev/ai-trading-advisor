"""Deterministic Setup Construction.

Converts one already-produced ``StrategyPolicyResult`` into a concrete
entry/reference price, protective ``stop_loss`` and ``risk_per_unit`` per
Policy-``ELIGIBLE_FOR_RISK_REVIEW`` family - the bridge Stage 7
``CandidateRiskInput`` and later Stage 10C/10E broker sizing/tracking need.
Never invokes Router/Judge/Policy/Risk/Portfolio/Session, never touches MT5,
the filesystem, or the wall clock, never performs I/O - a pure, synchronous,
stateless function of its explicit inputs only.

Reads only ``PolicyFamilyVerdict``, the already-authorized
``JudgeFamilyResult.direction``, and two caller-supplied facts a future
runtime orchestrator gathers once per cycle and reuses unchanged: one MT5
symbol-facts read (``MT5SymbolFacts``) and one M15 ``MarketStructureFeatures``
block from the SAME Stage 3A computation already run this cycle to feed
Judge - never a second, independent read of either, and never any other
Technical/Flow/External Intelligence fact. Whether a family's structural
thesis has a defensible entry/stop is exactly the information this module is
allowed to act on; which direction a family favors is Stage 6B Judge's
question, answered upstream, never re-asked here.

Direction is never decided here (``DirectionalCandidate ->
TradeDirection`` is a fixed, total, fail-closed mapping of Judge's own
output, never a new directional judgment). Monetary risk allocation remains
Stage 7/8/9's exclusive authority; broker volume sizing remains Stage 10C's
exclusive authority - this module produces ``risk_per_unit`` only, never a
lot size, and never calls ``app.mt5.sizing``.

``MEAN_REVERSION`` and ``EVENT_DRIVEN`` are approved V1
``FAMILY_SETUP_UNAVAILABLE`` abstentions: no ATR/percentage/arbitrary
fallback stop is ever computed for either, per the approved Setup
Construction design.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from app.core.config.constants import SIGNAL_EXECUTION_WINDOW
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.quality import FeatureQuality
from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_judge import DirectionalCandidate
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.enums.trade import TradeDirection
from app.core.models.base import Price, Symbol, Timestamp
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.risk_gate_result import CandidateRiskInput
from app.core.models.setup_construction import CandidateTradeSetup, SetupConstructionResult, StrategySetupResult

_DIRECTION_MAP: dict[DirectionalCandidate, TradeDirection] = {
    DirectionalCandidate.LONG_CANDIDATE: TradeDirection.LONG,
    DirectionalCandidate.SHORT_CANDIDATE: TradeDirection.SHORT,
}

_BREAK_DIRECTION_MAP: dict[BreakDirection, DirectionalCandidate] = {
    BreakDirection.UPWARD_BREAK: DirectionalCandidate.LONG_CANDIDATE,
    BreakDirection.DOWNWARD_BREAK: DirectionalCandidate.SHORT_CANDIDATE,
}

_ALLOWED_STRUCTURE_QUALITIES: frozenset[FeatureQuality] = frozenset({FeatureQuality.VALID, FeatureQuality.PARTIAL})
"""Mirrors ``app.decision.gate``'s own ``_ALLOWED_EVIDENCE_QUALITIES`` -
a locally-owned copy, not imported from it, per this repository's own
established precedent of each stage reimplementing its own narrow policy
primitive rather than sharing one cross-stage."""

_UNAVAILABLE_FAMILIES: frozenset[StrategyFamily] = frozenset({StrategyFamily.MEAN_REVERSION, StrategyFamily.EVENT_DRIVEN})
_STRUCTURE_FAMILIES: frozenset[StrategyFamily] = frozenset({StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT})

_StopSelector = Callable[[TradeDirection, MarketStructureFeatures], "Price | None"]


def _blocked(family: StrategyFamily, reason: SetupBlockReason) -> SetupConstructionResult:
    return SetupConstructionResult(family=family, outcome=SetupConstructionOutcome.BLOCKED, reasons=(reason,))


def _symbol_facts_usable(symbol_facts: MT5SymbolFacts | None) -> bool:
    if symbol_facts is None:
        return False
    return symbol_facts.trade_tick_size > 0 and symbol_facts.trade_tick_value_loss > 0


def _structure_usable(market_structure: MarketStructureFeatures | None) -> bool:
    if market_structure is None:
        return False
    return market_structure.status.quality in _ALLOWED_STRUCTURE_QUALITIES


def _resolve_entry_price(direction: TradeDirection, symbol_facts: MT5SymbolFacts) -> Decimal:
    return symbol_facts.ask if direction is TradeDirection.LONG else symbol_facts.bid


def _select_trend_following_stop(direction: TradeDirection, market_structure: MarketStructureFeatures) -> Decimal | None:
    """Most recent confirmed opposite-kind ``SwingPoint``, by ``candle_time``
    - LONG requires a LOW swing (support), SHORT requires a HIGH swing
    (resistance)."""
    required_kind = SwingKind.LOW if direction is TradeDirection.LONG else SwingKind.HIGH
    candidates = tuple(swing for swing in market_structure.swings if swing.kind is required_kind)
    if not candidates:
        return None
    return max(candidates, key=lambda swing: swing.candle_time).price


def _select_breakout_stop(direction: TradeDirection, market_structure: MarketStructureFeatures) -> Decimal | None:
    """The latest confirmed break - ``breaks[-1]``, mirroring
    ``app.technical_analysts.market_structure.MarketStructureAnalyst``'s own
    established "latest break" convention verbatim, never an independent
    re-sort by ``break_candle_time``. The mapped break direction must agree
    with the already-authorized Judge thesis; a disagreement fails closed
    exactly like an absent break - both are "the required M15 structure is
    not usable for this thesis," per the approved design."""
    if not market_structure.breaks:
        return None
    latest = market_structure.breaks[-1]
    mapped_direction = _BREAK_DIRECTION_MAP.get(latest.direction)
    expected_direction = DirectionalCandidate.LONG_CANDIDATE if direction is TradeDirection.LONG else DirectionalCandidate.SHORT_CANDIDATE
    if mapped_direction is not expected_direction:
        return None
    return latest.broken_swing.price


def _validate_geometry(direction: TradeDirection, entry_price: Decimal, stop_loss: Decimal) -> bool:
    if direction is TradeDirection.LONG:
        return stop_loss < entry_price
    return stop_loss > entry_price


def _compute_risk_per_unit(entry_price: Decimal, stop_loss: Decimal, symbol_facts: MT5SymbolFacts) -> Decimal:
    price_distance = abs(entry_price - stop_loss)
    return (price_distance / symbol_facts.trade_tick_size) * symbol_facts.trade_tick_value_loss


def _construct_structural_family(
    *,
    family: StrategyFamily,
    trade_direction: TradeDirection,
    symbol: Symbol,
    as_of: Timestamp,
    symbol_facts: MT5SymbolFacts | None,
    m15_market_structure: MarketStructureFeatures | None,
    select_stop: _StopSelector,
) -> SetupConstructionResult:
    if not _symbol_facts_usable(symbol_facts):
        return _blocked(family, SetupBlockReason.SHARED_FACT_UNAVAILABLE)
    assert symbol_facts is not None  # narrowed by _symbol_facts_usable

    if not _structure_usable(m15_market_structure):
        return _blocked(family, SetupBlockReason.SHARED_FACT_UNAVAILABLE)
    assert m15_market_structure is not None  # narrowed by _structure_usable

    stop_loss = select_stop(trade_direction, m15_market_structure)
    if stop_loss is None:
        return _blocked(family, SetupBlockReason.MISSING_STOP_REFERENCE)

    entry_price = _resolve_entry_price(trade_direction, symbol_facts)

    if not _validate_geometry(trade_direction, entry_price, stop_loss):
        return _blocked(family, SetupBlockReason.INVALID_STOP_SIDE)

    risk_per_unit = _compute_risk_per_unit(entry_price, stop_loss, symbol_facts)

    setup = CandidateTradeSetup(
        family=family,
        direction=trade_direction,
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit_levels=(),
        risk_per_unit=risk_per_unit,
        signal_time=as_of,
        valid_until=as_of + SIGNAL_EXECUTION_WINDOW,
    )
    return SetupConstructionResult(family=family, outcome=SetupConstructionOutcome.CONSTRUCTED, setup=setup)


class SetupConstruction:
    """Deterministic Setup Construction aggregator over one
    ``StrategyPolicyResult``."""

    def construct(
        self,
        *,
        strategy_policy_result: StrategyPolicyResult,
        as_of: Timestamp,
        symbol_facts: MT5SymbolFacts | None,
        m15_market_structure: MarketStructureFeatures | None,
    ) -> StrategySetupResult:
        symbol = strategy_policy_result.strategy_judge_result.strategy_router_result.market_evaluation.context.symbol

        family_results: list[SetupConstructionResult] = []
        for policy_result, judge_result in zip(
            strategy_policy_result.family_results,
            strategy_policy_result.strategy_judge_result.family_results,
            strict=True,
        ):
            if policy_result.verdict is not PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW:
                continue

            family = policy_result.family

            if family in _UNAVAILABLE_FAMILIES:
                family_results.append(_blocked(family, SetupBlockReason.FAMILY_SETUP_UNAVAILABLE))
                continue

            if family not in _STRUCTURE_FAMILIES:
                raise AssertionError(f"unhandled StrategyFamily {family!r}")

            assert judge_result.direction is not None  # guaranteed: ELIGIBLE_FOR_RISK_REVIEW implies JudgeOutcome.DIRECTIONAL
            trade_direction = _DIRECTION_MAP.get(judge_result.direction)
            if trade_direction is None:
                raise AssertionError(f"unhandled DirectionalCandidate {judge_result.direction!r}")

            select_stop = _select_trend_following_stop if family is StrategyFamily.TREND_FOLLOWING else _select_breakout_stop

            family_results.append(
                _construct_structural_family(
                    family=family,
                    trade_direction=trade_direction,
                    symbol=symbol,
                    as_of=as_of,
                    symbol_facts=symbol_facts,
                    m15_market_structure=m15_market_structure,
                    select_stop=select_stop,
                )
            )

        return StrategySetupResult(strategy_policy_result=strategy_policy_result, family_results=tuple(family_results))


def to_candidate_risk_inputs(strategy_setup_result: StrategySetupResult) -> tuple[CandidateRiskInput, ...]:
    """Pure compatibility bridge into the existing, unmodified ``RiskGate``
    contract only - never a replacement for retaining
    ``StrategySetupResult`` itself, which remains the sole carrier of the
    real setup failure reason. A BLOCKED family's ``Decimal("0")`` sentinel
    is only ever interpreted by ``RiskGate``'s own existing
    ``ZERO_OR_NEGATIVE_RISK_PER_UNIT`` business rule - never treated as the
    setup explanation itself. Produces exactly one ``CandidateRiskInput`` per
    entry in ``strategy_setup_result.family_results``, satisfying
    ``RiskGate``'s per-Policy-eligible-family coverage requirement without
    any change to ``app.risk.engine``.
    """
    return tuple(
        CandidateRiskInput(
            family=result.family,
            risk_per_unit=(
                result.setup.risk_per_unit if result.outcome is SetupConstructionOutcome.CONSTRUCTED else Decimal("0")
            ),
        )
        for result in strategy_setup_result.family_results
    )


__all__ = ["SetupConstruction", "to_candidate_risk_inputs"]
