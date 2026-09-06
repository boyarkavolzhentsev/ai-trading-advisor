"""Final Recommendation -> Stage 10E tracking-creation integration output
contract (Final Runtime Integration, Part E).

Pairs one ACTIONABLE ``FinalRecommendation``'s existing, unmodified Stage 10E
``MT5TrackedRecommendationCreationResult`` (see ``app.mt5.tracker.
create_tracked_recommendation``) with its durable ``FinalRecommendationProvenance``
(see the approved Part E corrective design) - the two facts a caller
constructs together, at issuance time, for the same ``trade_id``, but never
merges into one schema: matching-creation state and recommendation
provenance remain separate persisted concerns (see
``app.mt5.recommendation_persistence`` vs. ``app.mt5.
recommendation_provenance_persistence``).

``trade_id`` is carried at the top level - not only inside ``provenance`` -
because ``tracking_creation_result.tracked_recommendation`` is absent under
``MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE``: a caller
must still be able to identify which recommendation this result is about
even when tracking creation itself failed closed. ``family`` is deliberately
never duplicated as a second top-level field - ``provenance`` is its sole
owner here, per the approved corrective design.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.models.base import DomainModel
from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance
from app.core.models.mt5_matching import MT5TrackedRecommendationCreationResult


class TrackedRecommendationConstructionResult(DomainModel):
    """One ACTIONABLE ``FinalRecommendation``'s Stage 10E tracking-creation
    attempt, paired with its durable provenance."""

    trade_id: Annotated[str, Field(min_length=1)]
    tracking_creation_result: MT5TrackedRecommendationCreationResult
    provenance: FinalRecommendationProvenance

    @model_validator(mode="after")
    def _validate_trade_id_matches_provenance(self) -> Self:
        if self.trade_id != self.provenance.trade_id:
            raise ValueError("trade_id must equal provenance.trade_id")
        return self

    @model_validator(mode="after")
    def _validate_trade_id_matches_tracking_creation_result(self) -> Self:
        if self.tracking_creation_result.outcome is MT5TrackedRecommendationCreationOutcome.CREATED:
            tracked = self.tracking_creation_result.tracked_recommendation
            assert tracked is not None  # guaranteed by CREATED
            if tracked.position_record.trade_id != self.trade_id:
                raise ValueError("tracking_creation_result's trade_id must equal trade_id")
        return self


__all__ = ["TrackedRecommendationConstructionResult"]
