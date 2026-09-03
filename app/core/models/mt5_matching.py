"""Stage 10E deterministic recommendation-to-broker matching output
contracts.

``MT5MatchResult`` is the outcome of one matching attempt (see
``app.mt5.matching``) - purely technical/procedural, never a business
lifecycle fact (see ``app.core.enums.mt5_matching.MT5MatchOutcome``'s own
docstring for why it is kept structurally separate from ``TradeStatus``).

``MT5TrackedRecommendationCreationResult`` is the outcome of one attempt to
create a fresh ``MT5TrackedRecommendation`` at recommendation-issuance time -
``CREATED`` only when the caller-supplied pre-existing-position snapshot was
itself confirmed safe (see ``app.core.enums.mt5_matching.
MT5TrackedRecommendationCreationOutcome``).
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_matching import MT5MatchOutcome, MT5TrackedRecommendationCreationOutcome
from app.core.models.base import DomainModel, Timestamp
from app.core.models.mt5_tracking import MT5TrackedRecommendation


class MT5MatchResult(DomainModel):
    """One deterministic recommendation <-> broker matching attempt.

    ``matched_position_id`` is present if and only if ``outcome`` is
    ``MATCHED``. ``candidate_position_ids`` carries the ``position_id``(s)
    the outcome is *about*: at least two (sorted ascending, duplicate-free)
    for ``AMBIGUOUS`` - V1 never selects a winner among them; at least one
    for ``PARTIAL_FILL``/``VOLUME_MISMATCH`` - the position_id(s) whose
    qualifying opening-fill total was inconclusive. Absent for every other
    outcome.
    """

    as_of: Timestamp
    outcome: MT5MatchOutcome
    matched_position_id: Annotated[int, Field(gt=0)] | None = None
    candidate_position_ids: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _validate_fields_match_outcome(self) -> Self:
        if self.outcome is MT5MatchOutcome.MATCHED:
            if self.matched_position_id is None:
                raise ValueError("MATCHED requires matched_position_id")
            if self.candidate_position_ids:
                raise ValueError("MATCHED must not carry candidate_position_ids")
        elif self.outcome is MT5MatchOutcome.AMBIGUOUS:
            if self.matched_position_id is not None:
                raise ValueError("AMBIGUOUS must not carry matched_position_id")
            if len(self.candidate_position_ids) < 2:
                raise ValueError("AMBIGUOUS requires at least two candidate_position_ids")
        elif self.outcome in (MT5MatchOutcome.PARTIAL_FILL, MT5MatchOutcome.VOLUME_MISMATCH):
            if self.matched_position_id is not None:
                raise ValueError(f"{self.outcome} must not carry matched_position_id")
            if not self.candidate_position_ids:
                raise ValueError(f"{self.outcome} requires at least one candidate_position_id")
        else:
            if self.matched_position_id is not None:
                raise ValueError(f"{self.outcome} must not carry matched_position_id")
            if self.candidate_position_ids:
                raise ValueError(f"{self.outcome} must not carry candidate_position_ids")
        return self

    @model_validator(mode="after")
    def _validate_candidate_ids_sorted_and_unique(self) -> Self:
        ids = list(self.candidate_position_ids)
        if ids != sorted(ids):
            raise ValueError("candidate_position_ids must be sorted ascending")
        if len(set(ids)) != len(ids):
            raise ValueError("candidate_position_ids must not contain duplicates")
        return self


class MT5TrackedRecommendationCreationResult(DomainModel):
    """Result of one ``create_tracked_recommendation`` call.

    ``tracked_recommendation`` is present if and only if ``outcome`` is
    ``CREATED`` - ``SNAPSHOT_UNAVAILABLE`` never carries a partially-built or
    best-effort tracking state.
    """

    as_of: Timestamp
    outcome: MT5TrackedRecommendationCreationOutcome
    tracked_recommendation: MT5TrackedRecommendation | None = None

    @model_validator(mode="after")
    def _validate_tracked_recommendation_presence(self) -> Self:
        if self.outcome is MT5TrackedRecommendationCreationOutcome.CREATED:
            if self.tracked_recommendation is None:
                raise ValueError("CREATED requires tracked_recommendation")
        else:
            if self.tracked_recommendation is not None:
                raise ValueError(f"{self.outcome} must not carry tracked_recommendation")
        return self


__all__ = ["MT5MatchResult", "MT5TrackedRecommendationCreationResult"]
