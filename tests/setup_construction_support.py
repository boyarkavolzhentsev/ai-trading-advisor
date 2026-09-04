"""Shared builders for Setup Construction tests.

Builds real ``StrategyPolicyResult`` fixtures via the real Stage 5A-6C
pipeline (reusing ``tests/policy_gate_support.py``/``tests/strategy_judge_support.py``
and their own upstream support modules) plus small, directly-constructed
``MarketStructureFeatures``/``MT5SymbolFacts`` shared-fact fixtures - Setup
Construction's own two caller-supplied inputs that no earlier stage produces.
Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.models.feature_status import FeatureStatus
from app.core.models.market_structure_features import MarketStructureFeatures, StructuralBreak, SwingPoint
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.setup_construction import SetupConstructionResult, StrategySetupResult
from app.core.models.strategy_judge_result import JudgeFamilyResult, StrategyJudgeResult
from app.decision.gate import PolicyGate
from tests.mt5_position_support import default_symbol_facts
from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge, technical_with_market_structure_break, technical_with_trend_observations
from tests.market_evaluation_support import NOW as EVALUATION_NOW
from tests.market_evaluation_support import SYMBOL, full_flow_result

__all__ = [
    "AS_OF",
    "SYMBOL",
    "breakout_policy_result",
    "combined_trend_following_and_breakout_policy_result",
    "event_driven_policy_result",
    "mean_reversion_synthetic_policy_result",
    "result_for",
    "structural_break",
    "swing",
    "symbol_facts",
    "trend_following_policy_result",
    "unusable_market_structure",
    "usable_market_structure",
]

AS_OF = EVALUATION_NOW
"""Setup Construction's own caller-supplied ``as_of`` - deliberately equal to
``MarketEvaluationResult.evaluation_time`` used by every upstream fixture, so
every constructed setup shares one coherent cycle timestamp."""

_STRUCTURE_TIME = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)


def result_for(strategy_setup_result: StrategySetupResult, family: StrategyFamily) -> SetupConstructionResult | None:
    matches = [r for r in strategy_setup_result.family_results if r.family is family]
    return matches[0] if matches else None


def trend_following_policy_result(*, direction: str = "UPWARD") -> StrategyPolicyResult:
    """A real Router/Judge/Policy chain with TREND_FOLLOWING (and
    MEAN_REVERSION, sharing the identical structural rule) both
    ``ELIGIBLE_FOR_RISK_REVIEW`` at ``DIRECTIONAL``/``direction``."""
    technical = technical_with_trend_observations(return_direction=direction, slope_direction=direction)
    router_result, judge_result = route_and_judge(technical=technical)
    return PolicyGate().apply(strategy_judge_result=judge_result)


def breakout_policy_result(*, break_direction: str = "UPWARD_BREAK") -> StrategyPolicyResult:
    """A real Router/Judge/Policy chain with BREAKOUT
    ``ELIGIBLE_FOR_RISK_REVIEW`` at ``DIRECTIONAL``/the mapped direction."""
    technical = technical_with_market_structure_break(break_direction=break_direction)
    router_result, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    return PolicyGate().apply(strategy_judge_result=judge_result)


def combined_trend_following_and_breakout_policy_result() -> StrategyPolicyResult:
    """A real Router/Judge/Policy chain with BOTH TREND_FOLLOWING and
    BREAKOUT simultaneously ``ELIGIBLE_FOR_RISK_REVIEW`` at ``DIRECTIONAL``/
    LONG - used to exercise multi-family independence: one family's setup
    outcome must never depend on, or affect, the other's."""
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK", return_direction="UPWARD")
    router_result, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    return PolicyGate().apply(strategy_judge_result=judge_result)


def event_driven_policy_result() -> StrategyPolicyResult:
    """A real Router/Judge/Policy chain with EVENT_DRIVEN
    ``ELIGIBLE_FOR_RISK_REVIEW`` - no price/structure fact is evidentially
    tied to its news-sentiment thesis."""
    external = external_with_news_sentiment(provider_signs={"provider_a": "POSITIVE", "provider_b": "POSITIVE"})
    router_result, judge_result = route_and_judge(external=external)
    return PolicyGate().apply(strategy_judge_result=judge_result)


def mean_reversion_synthetic_policy_result() -> StrategyPolicyResult:
    """Defensive-path fixture: MEAN_REVERSION never legitimately reaches
    ``JudgeOutcome.DIRECTIONAL`` via the real ``Judge`` (it always
    abstains - see ``app.judge.judge._judge_mean_reversion``), so this
    fixture substitutes a synthetic, fully-validated ``JudgeFamilyResult``
    for MEAN_REVERSION - reusing TREND_FOLLOWING's own real, in-bounds
    ``evidence_refs`` verbatim - to exercise Setup Construction's own
    defensive ``FAMILY_SETUP_UNAVAILABLE`` handling for a family the real
    pipeline can never itself route there. Every model still passes its own
    full validation; nothing is bypassed."""
    technical = technical_with_trend_observations(return_direction="UPWARD", slope_direction="UPWARD")
    router_result, real_judge_result = route_and_judge(technical=technical)
    trend_following_result = next(r for r in real_judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_following_result.outcome is JudgeOutcome.DIRECTIONAL

    synthetic_mean_reversion = JudgeFamilyResult(
        family=StrategyFamily.MEAN_REVERSION,
        outcome=JudgeOutcome.DIRECTIONAL,
        direction=trend_following_result.direction,
        evidence_refs=trend_following_result.evidence_refs,
    )
    family_results = tuple(
        synthetic_mean_reversion if r.family is StrategyFamily.MEAN_REVERSION else r for r in real_judge_result.family_results
    )
    judge_result = StrategyJudgeResult(strategy_router_result=router_result, family_results=family_results)
    return PolicyGate().apply(strategy_judge_result=judge_result)


def symbol_facts(**overrides: object) -> MT5SymbolFacts:
    fields: dict[str, object] = {"symbol": SYMBOL, "bid": Decimal("100"), "ask": Decimal("100.10")}
    fields.update(overrides)
    return default_symbol_facts(**fields)


def swing(
    *, kind: SwingKind, price: Decimal, candle_time: datetime = _STRUCTURE_TIME, confirmed_offset: timedelta = timedelta(minutes=15)
) -> SwingPoint:
    return SwingPoint(
        kind=kind, candle_time=candle_time, price=price, confirmed_at=candle_time + confirmed_offset, left_bars=2, right_bars=2
    )


def structural_break(
    *, broken_swing: SwingPoint, break_close: Decimal, direction: BreakDirection, break_candle_time: datetime | None = None
) -> StructuralBreak:
    candle_time = break_candle_time if break_candle_time is not None else broken_swing.confirmed_at + timedelta(minutes=15)
    return StructuralBreak(
        direction=direction, broken_swing=broken_swing, break_candle_time=candle_time, break_close=break_close, confirmed_at=candle_time
    )


def usable_market_structure(
    *,
    swings: tuple[SwingPoint, ...] = (),
    breaks: tuple[StructuralBreak, ...] = (),
    quality: FeatureQuality = FeatureQuality.VALID,
    symbol: str = SYMBOL,
) -> MarketStructureFeatures:
    return MarketStructureFeatures(
        symbol=symbol,
        contract_type=ContractType.PERPETUAL,
        timeframe=Timeframe.M15,
        left_bars=2,
        right_bars=2,
        swings=swings,
        breaks=breaks,
        status=FeatureStatus(quality=quality, sample_count=len(swings) + len(breaks)),
        source="test",
    )


def unusable_market_structure(*, quality: FeatureQuality) -> MarketStructureFeatures:
    """Any structure block below Setup Construction's approved quality
    allowlist - carries no swing/break regardless, since it is never
    trusted."""
    return usable_market_structure(quality=quality)
