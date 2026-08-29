"""Stage 6A models must never carry a ranking, score, weight, vote,
strength, dimension count, preferred strategy, or winner - eligibility is
categorical only.

Checks ``model_fields`` directly rather than scanning source text, so a
docstring explaining *why* such a field is absent can never trip this guard.
"""

from __future__ import annotations

from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "score",
        "confidence",
        "weight",
        "weights",
        "vote",
        "votes",
        "rank",
        "ranking",
        "strength",
        "supporting_dimension_count",
        "preferred_strategy",
        "winner",
    }
)


def test_eligibility_entry_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(StrategyEligibilityEntry.model_fields)


def test_router_result_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(StrategyRouterResult.model_fields)
