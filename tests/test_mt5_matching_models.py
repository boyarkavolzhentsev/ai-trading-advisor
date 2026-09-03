"""Stage 10E model validation: ``MT5MatchResult``,
``MT5TrackedRecommendationCreationResult``, ``MT5TrackedRecommendation``,
``MT5PositionLifecycleAssessment``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.mt5_history import MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.enums.mt5_matching import MT5MatchOutcome, MT5TrackedRecommendationCreationOutcome
from app.core.enums.trade import TradeStatus
from app.core.models.mt5_matching import MT5MatchResult, MT5TrackedRecommendationCreationResult
from app.core.models.mt5_tracking import MT5PositionLifecycleAssessment, MT5TrackedRecommendation
from tests.mt5_matching_support import SIGNAL_TIME, default_position_record, default_tracked_recommendation

# --- MT5MatchResult ---


def test_matched_requires_matched_position_id() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.MATCHED)


def test_matched_must_not_carry_candidates() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.MATCHED, matched_position_id=1, candidate_position_ids=(1, 2))


def test_ambiguous_requires_two_candidates() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.AMBIGUOUS, candidate_position_ids=(1,))


def test_ambiguous_must_not_carry_matched_position_id() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.AMBIGUOUS, matched_position_id=1, candidate_position_ids=(1, 2))


def test_non_matched_must_not_carry_matched_position_id() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.NO_CANDIDATE_YET, matched_position_id=1)


def test_candidate_ids_must_be_sorted() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.AMBIGUOUS, candidate_position_ids=(2, 1))


def test_candidate_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.AMBIGUOUS, candidate_position_ids=(1, 1))


def test_matched_valid_construction() -> None:
    result = MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.MATCHED, matched_position_id=42)
    assert result.matched_position_id == 42


def test_partial_fill_requires_at_least_one_candidate() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.PARTIAL_FILL)


def test_partial_fill_must_not_carry_matched_position_id() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.PARTIAL_FILL, matched_position_id=1, candidate_position_ids=(1,))


def test_partial_fill_valid_construction() -> None:
    result = MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.PARTIAL_FILL, candidate_position_ids=(7001,))
    assert result.candidate_position_ids == (7001,)


def test_volume_mismatch_requires_at_least_one_candidate() -> None:
    with pytest.raises(ValidationError):
        MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.VOLUME_MISMATCH)


def test_volume_mismatch_valid_construction() -> None:
    result = MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.VOLUME_MISMATCH, candidate_position_ids=(7001,))
    assert result.candidate_position_ids == (7001,)


def test_volume_mismatch_may_carry_multiple_candidates() -> None:
    result = MT5MatchResult(as_of=SIGNAL_TIME, outcome=MT5MatchOutcome.VOLUME_MISMATCH, candidate_position_ids=(1001, 2002))
    assert result.candidate_position_ids == (1001, 2002)


# --- MT5TrackedRecommendationCreationResult ---


def test_created_requires_tracked_recommendation() -> None:
    with pytest.raises(ValidationError):
        MT5TrackedRecommendationCreationResult(as_of=SIGNAL_TIME, outcome=MT5TrackedRecommendationCreationOutcome.CREATED)


def test_snapshot_unavailable_must_not_carry_tracked_recommendation() -> None:
    with pytest.raises(ValidationError):
        MT5TrackedRecommendationCreationResult(
            as_of=SIGNAL_TIME,
            outcome=MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE,
            tracked_recommendation=default_tracked_recommendation(),
        )


def test_created_valid_construction() -> None:
    result = MT5TrackedRecommendationCreationResult(
        as_of=SIGNAL_TIME, outcome=MT5TrackedRecommendationCreationOutcome.CREATED, tracked_recommendation=default_tracked_recommendation()
    )
    assert result.tracked_recommendation is not None


# --- MT5TrackedRecommendation ---


def test_pre_existing_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        default_tracked_recommendation(pre_existing_position_ids=(1, 1))


def test_matched_id_must_not_be_pre_existing() -> None:
    with pytest.raises(ValidationError):
        default_tracked_recommendation(
            pre_existing_position_ids=(500,),
            matched_position_id=500,
            position_record=default_position_record(status=TradeStatus.OPEN),
        )


def test_matched_id_requires_post_match_status() -> None:
    with pytest.raises(ValidationError):
        default_tracked_recommendation(matched_position_id=500, position_record=default_position_record(status=TradeStatus.PENDING))


def test_unmatched_requires_pre_match_status() -> None:
    with pytest.raises(ValidationError):
        default_tracked_recommendation(position_record=default_position_record(status=TradeStatus.OPEN))


def test_unmatched_pending_is_valid() -> None:
    tracked = default_tracked_recommendation()
    assert tracked.matched_position_id is None
    assert tracked.position_record.status is TradeStatus.PENDING


def test_unmatched_not_filled_is_valid() -> None:
    tracked = default_tracked_recommendation(position_record=default_position_record(status=TradeStatus.NOT_FILLED))
    assert tracked.position_record.status is TradeStatus.NOT_FILLED


def test_matched_open_is_valid() -> None:
    tracked = default_tracked_recommendation(matched_position_id=500, position_record=default_position_record(status=TradeStatus.OPEN))
    assert tracked.matched_position_id == 500


def test_tracked_recommendation_mutable() -> None:
    tracked = default_tracked_recommendation()
    tracked.last_read_at = SIGNAL_TIME
    assert tracked.last_read_at == SIGNAL_TIME


# --- MT5PositionLifecycleAssessment ---


def test_ready_open_requires_entry_fields() -> None:
    with pytest.raises(ValidationError):
        MT5PositionLifecycleAssessment(as_of=SIGNAL_TIME, position_id=1, outcome=MT5RealizedPnLOutcome.READY, is_fully_closed=False)


def test_ready_open_must_not_carry_exit_fields() -> None:
    with pytest.raises(ValidationError):
        MT5PositionLifecycleAssessment(
            as_of=SIGNAL_TIME,
            position_id=1,
            outcome=MT5RealizedPnLOutcome.READY,
            is_fully_closed=False,
            actual_entry=Decimal("100"),
            actual_entry_time=SIGNAL_TIME,
            realized_pnl=Decimal("0"),
            exit_price=Decimal("100"),
        )


def test_ready_closed_requires_exit_fields() -> None:
    with pytest.raises(ValidationError):
        MT5PositionLifecycleAssessment(
            as_of=SIGNAL_TIME,
            position_id=1,
            outcome=MT5RealizedPnLOutcome.READY,
            is_fully_closed=True,
            actual_entry=Decimal("100"),
            actual_entry_time=SIGNAL_TIME,
            realized_pnl=Decimal("0"),
        )


def test_ready_open_valid() -> None:
    assessment = MT5PositionLifecycleAssessment(
        as_of=SIGNAL_TIME,
        position_id=1,
        outcome=MT5RealizedPnLOutcome.READY,
        is_fully_closed=False,
        actual_entry=Decimal("100"),
        actual_entry_time=SIGNAL_TIME,
        realized_pnl=Decimal("-2"),
    )
    assert assessment.is_fully_closed is False


def test_ready_closed_valid() -> None:
    assessment = MT5PositionLifecycleAssessment(
        as_of=SIGNAL_TIME,
        position_id=1,
        outcome=MT5RealizedPnLOutcome.READY,
        is_fully_closed=True,
        actual_entry=Decimal("100"),
        actual_entry_time=SIGNAL_TIME,
        exit_price=Decimal("105"),
        exit_time=SIGNAL_TIME,
        realized_pnl=Decimal("46"),
    )
    assert assessment.realized_pnl == Decimal("46")


def test_blocked_requires_reasons_and_tickets() -> None:
    with pytest.raises(ValidationError):
        MT5PositionLifecycleAssessment(as_of=SIGNAL_TIME, position_id=1, outcome=MT5RealizedPnLOutcome.BLOCKED)


def test_blocked_must_not_carry_ready_fields() -> None:
    with pytest.raises(ValidationError):
        MT5PositionLifecycleAssessment(
            as_of=SIGNAL_TIME,
            position_id=1,
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE,),
            unsafe_deal_tickets=(1,),
            realized_pnl=Decimal("0"),
        )


def test_blocked_valid() -> None:
    assessment = MT5PositionLifecycleAssessment(
        as_of=SIGNAL_TIME,
        position_id=1,
        outcome=MT5RealizedPnLOutcome.BLOCKED,
        blocked_reasons=(MT5RealizedPnLBlockReason.UNSUPPORTED_OUT_BY,),
        unsafe_deal_tickets=(1,),
    )
    assert assessment.outcome is MT5RealizedPnLOutcome.BLOCKED
