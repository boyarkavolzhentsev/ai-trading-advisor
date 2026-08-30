"""Stage 6C must never derive, create, or duplicate direction: it reads only
``JudgeOutcome`` and observation-level ``FeatureQuality``, never any
observation's own ``.value``, and never mints a LONG/SHORT/*_CANDIDATE state
of its own. Direction stays accessible only through the embedded
``StrategyJudgeResult``."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.core.enums.strategy_judge import DirectionalCandidate
from app.core.enums.strategy_router import StrategyFamily
from app.decision.gate import PolicyGate
from app.core.models.policy_gate_result import PolicyFamilyResult, StrategyPolicyResult
from tests.market_evaluation_support import full_technical_result
from tests.policy_gate_support import route_judge_and_gate


def test_gate_source_never_reads_observation_value_attribute() -> None:
    """AST check: no ``.value`` attribute access anywhere in gate.py -
    Policy Gate resolves quality only, never semantic value content."""
    path = Path(inspect.getfile(PolicyGate))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "value":
            raise AssertionError("gate.py accesses a '.value' attribute - Policy Gate must never read observation.value")


def test_gate_source_never_references_directional_candidate_members() -> None:
    path = Path(inspect.getfile(PolicyGate))
    source = path.read_text(encoding="utf-8")
    for forbidden in ("DirectionalCandidate", "LONG_CANDIDATE", "SHORT_CANDIDATE", "LONG", "SHORT"):
        assert forbidden not in source, f"gate.py references forbidden directional vocabulary: {forbidden!r}"


def test_policy_family_result_carries_no_direction_field() -> None:
    assert "direction" not in PolicyFamilyResult.model_fields
    assert DirectionalCandidate.__name__ not in str(PolicyFamilyResult.model_fields)


def test_strategy_policy_result_carries_no_top_level_direction_field() -> None:
    assert "direction" not in StrategyPolicyResult.model_fields


def test_direction_recoverable_only_through_embedded_judge_result() -> None:
    _, judge_result, policy_result = route_judge_and_gate(technical=full_technical_result())
    trend_judge = next(r for r in judge_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    trend_policy = next(r for r in policy_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)

    # The only place a direction value exists at all is inside the embedded
    # strategy_judge_result - recoverable by matching family/index, never
    # duplicated onto the policy family result itself.
    assert trend_judge.direction is DirectionalCandidate.LONG_CANDIDATE
    assert not hasattr(trend_policy, "direction")
    matching = next(r for r in policy_result.strategy_judge_result.family_results if r.family == trend_policy.family)
    assert matching.direction is trend_judge.direction
