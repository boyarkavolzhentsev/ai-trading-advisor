"""Stage 6C models must never carry a confidence, score, weight, rank,
probability, free-text reasoning/explanation, generic metadata dict,
timestamp, or copied direction/evidence payload - and must never introduce
execution-authorization vocabulary."""

from __future__ import annotations

from app.core.models.policy_gate_result import PolicyEvidenceQualityViolation, PolicyFamilyResult, StrategyPolicyResult

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
        "reasoning",
        "explanation",
        "metadata",
        "timestamp",
        "policy_time",
        "gate_time",
        "analysis_time",
        "direction",
        "evidence",
        "evidence_refs",
        "approved",
        "approved_trade",
        "execute",
        "executable",
        "send_order",
        "place_order",
        "entry",
        "stop_loss",
        "take_profit",
        "quantity",
        "lot_size",
        "risk_percent",
        "max_loss",
        "broker_order_type",
        "ticket",
        "valid_until",
    }
)


def test_violation_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(PolicyEvidenceQualityViolation.model_fields)


def test_family_result_has_no_forbidden_fields() -> None:
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(PolicyFamilyResult.model_fields)


def test_strategy_policy_result_has_no_forbidden_fields() -> None:
    # strategy_judge_result is an allowed embedded-object field name, not a
    # forbidden bare "evidence"/"direction" field - checked separately below.
    fields = set(StrategyPolicyResult.model_fields) - {"strategy_judge_result"}
    assert FORBIDDEN_FIELD_NAMES.isdisjoint(fields)


def test_no_execution_authorization_vocabulary_anywhere() -> None:
    execution_fields = {
        "approved",
        "approved_trade",
        "execute",
        "executable",
        "send_order",
        "place_order",
        "entry_price",
        "entry",
        "stop_loss",
        "take_profit",
        "valid_until",
        "signal_time",
        "lot_size",
        "quantity",
        "order_id",
        "broker_order_type",
        "ticket",
    }
    assert execution_fields.isdisjoint(PolicyFamilyResult.model_fields)
    assert execution_fields.isdisjoint(StrategyPolicyResult.model_fields)
    assert execution_fields.isdisjoint(PolicyEvidenceQualityViolation.model_fields)


def test_policy_family_result_reason_verdict_vocabulary_only() -> None:
    """The only PolicyFamilyVerdict members are ELIGIBLE_FOR_RISK_REVIEW and
    BLOCKED - never APPROVE/REJECT/WAIT."""
    from app.core.enums.policy_gate import PolicyFamilyVerdict

    assert set(PolicyFamilyVerdict) == {PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW, PolicyFamilyVerdict.BLOCKED}
    for member in PolicyFamilyVerdict:
        assert member.value not in {"APPROVE", "REJECT", "WAIT"}
