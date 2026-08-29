"""Stage 6B models must never carry a confidence, score, weight, rank,
probability, free-text reasoning/explanation, or generic metadata dict."""

from __future__ import annotations

from app.core.models.strategy_judge_result import JudgeEvidenceRef, JudgeFamilyResult, StrategyJudgeResult

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
        "probability",
        "strength",
        "reason",
        "reasons",
        "reasoning",
        "explanation",
        "metadata",
        "timestamp",
        "judge_time",
        "analysis_time",
    }
)


def test_evidence_ref_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(JudgeEvidenceRef.model_fields)


def test_family_result_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(JudgeFamilyResult.model_fields)


def test_strategy_judge_result_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(StrategyJudgeResult.model_fields)


def test_no_execution_fields_anywhere() -> None:
    execution_fields = {"entry_price", "stop_loss", "take_profit", "valid_until", "signal_time", "lot_size", "order_id"}
    assert execution_fields.isdisjoint(JudgeFamilyResult.model_fields)
    assert execution_fields.isdisjoint(StrategyJudgeResult.model_fields)
