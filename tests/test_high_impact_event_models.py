"""High-Impact Event Risk Gate model/enum validation (Corrective V1
Integration, test group A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.enums.high_impact_event import (
    HighImpactEventBlockReason,
    HighImpactEventDataQuality,
    HighImpactEventImportance,
    HighImpactEventVerdict,
)
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.high_impact_event import (
    HighImpactEventContext,
    HighImpactEventFamilyResult,
    HighImpactEventRecord,
    HighImpactEventRiskResult,
)
from tests.high_impact_event_support import EVENT_TIME, record

NOW = EVENT_TIME - timedelta(minutes=20)


def test_enums_have_exact_expected_members() -> None:
    assert {m.value for m in HighImpactEventVerdict} == {"ALLOWED", "WARNED", "BLOCKED"}
    assert {m.value for m in HighImpactEventBlockReason} == {"EVENT_WINDOW_OVERLAP"}
    assert {m.value for m in HighImpactEventDataQuality} == {"FRESH", "STALE", "UNAVAILABLE", "MALFORMED"}
    assert {m.value for m in HighImpactEventImportance} == {"NONE", "LOW", "MODERATE", "HIGH"}


def test_record_has_no_release_value_fields() -> None:
    """No actual/forecast/previous/revision/impact-direction field exists."""
    forbidden = {"actual", "forecast", "previous", "revision", "revision_number", "impact", "impact_type"}
    assert forbidden.isdisjoint(HighImpactEventRecord.model_fields)


def test_family_result_reasons_empty_unless_blocked() -> None:
    with pytest.raises(ValidationError, match="reasons must be empty"):
        HighImpactEventFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=HighImpactEventVerdict.ALLOWED,
            reasons=(HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,),
            data_quality=HighImpactEventDataQuality.FRESH,
        )


def test_blocked_requires_event_window_overlap_reason() -> None:
    with pytest.raises(ValidationError, match="BLOCKED requires exactly"):
        HighImpactEventFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=HighImpactEventVerdict.BLOCKED,
            reasons=(),
            next_safe_time=NOW,
            data_quality=HighImpactEventDataQuality.FRESH,
        )


def test_blocked_requires_next_safe_time() -> None:
    with pytest.raises(ValidationError, match="BLOCKED requires next_safe_time"):
        HighImpactEventFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=HighImpactEventVerdict.BLOCKED,
            reasons=(HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,),
            next_safe_time=None,
            data_quality=HighImpactEventDataQuality.FRESH,
        )


def test_non_blocked_must_not_carry_next_safe_time() -> None:
    with pytest.raises(ValidationError, match="next_safe_time must be None"):
        HighImpactEventFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=HighImpactEventVerdict.WARNED,
            next_safe_time=NOW,
            data_quality=HighImpactEventDataQuality.FRESH,
        )


def test_relevant_events_must_be_deterministically_ordered() -> None:
    early = record(event_time=EVENT_TIME - timedelta(days=1), provider_event_id="a")
    late = record(event_time=EVENT_TIME, provider_event_id="b")
    with pytest.raises(ValidationError, match="relevant_events must be ordered"):
        HighImpactEventFamilyResult(
            family=StrategyFamily.TREND_FOLLOWING,
            verdict=HighImpactEventVerdict.ALLOWED,
            relevant_events=(late, early),
            data_quality=HighImpactEventDataQuality.FRESH,
        )


def test_no_duplicate_family_results() -> None:
    fr = HighImpactEventFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, verdict=HighImpactEventVerdict.ALLOWED, data_quality=HighImpactEventDataQuality.FRESH
    )
    with pytest.raises(ValidationError, match="must not contain duplicate"):
        HighImpactEventRiskResult(as_of=NOW, family_results=(fr, fr), producer="test")


def test_canonical_family_order_enforced() -> None:
    breakout = HighImpactEventFamilyResult(
        family=StrategyFamily.BREAKOUT, verdict=HighImpactEventVerdict.ALLOWED, data_quality=HighImpactEventDataQuality.FRESH
    )
    trend = HighImpactEventFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING, verdict=HighImpactEventVerdict.ALLOWED, data_quality=HighImpactEventDataQuality.FRESH
    )
    with pytest.raises(ValidationError, match="canonical StrategyFamily order"):
        HighImpactEventRiskResult(as_of=NOW, family_results=(breakout, trend), producer="test")


def test_context_events_must_be_empty_unless_fresh() -> None:
    with pytest.raises(ValidationError, match="events must be empty"):
        HighImpactEventContext(events=(record(),), data_quality=HighImpactEventDataQuality.STALE, producer="test", generated_at=NOW)


def test_context_generated_at_must_be_none_for_unavailable() -> None:
    with pytest.raises(ValidationError, match="generated_at must be None"):
        HighImpactEventContext(events=(), data_quality=HighImpactEventDataQuality.UNAVAILABLE, producer="test", generated_at=NOW)


def test_no_direction_confidence_or_probability_fields_anywhere() -> None:
    forbidden = {"direction", "confidence", "probability", "score"}
    for model in (HighImpactEventRecord, HighImpactEventFamilyResult, HighImpactEventRiskResult, HighImpactEventContext):
        assert forbidden.isdisjoint(model.model_fields), model


def test_models_are_frozen() -> None:
    rec = record()
    with pytest.raises(ValidationError):
        rec.event_code = "OTHER"  # type: ignore[misc]
