"""Stage 10E persisted recommendation-tracking and position-lifecycle output
contracts.

``MT5TrackedRecommendation`` is the one Stage 10E persists per ``trade_id``:
it embeds the mutable ``PositionRecord`` Stage 9 already owns (never
duplicating its fields) alongside the additional facts Stage 10E's matching
policy needs that ``PositionRecord`` was never extended to carry -
``approved_broker_volume`` (Stage 10C's broker-normalized volume has no
other home; see ``app.mt5.matching``) and the confirmed pre-existing-position
snapshot/broker linkage matching requires. One persisted document per
recommendation avoids a two-store desync problem a separate PositionRecord
store and a separate tracking-state store would create.

``MT5PositionLifecycleAssessment`` reuses Stage 10D's own
``MT5RealizedPnLOutcome``/``MT5RealizedPnLBlockReason`` vocabulary (never a
duplicate financial-semantic enum) for the same READY/BLOCKED, all-or-
nothing philosophy, applied to one matched broker ``position_id``'s complete
deal history instead of one broker trading day.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.mt5_history import MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.enums.mt5_matching import MT5MatchOutcome
from app.core.enums.trade import TradeStatus
from app.core.models.base import DomainModel, MutableDomainModel, Price, Timestamp
from app.core.models.position import PositionRecord

_LIFECYCLE_REASON_ORDER: tuple[MT5RealizedPnLBlockReason, ...] = tuple(MT5RealizedPnLBlockReason)

_POST_MATCH_STATUSES: frozenset[TradeStatus] = frozenset(
    {TradeStatus.OPEN, TradeStatus.WIN, TradeStatus.LOSS, TradeStatus.BREAKEVEN}
)
"""The only ``TradeStatus`` values Stage 10E ever assigns once a
recommendation has been matched to a broker ``position_id`` - see
``app.mt5.tracker`` for the exact transitions (``FILLED``/``CLOSED`` are
deliberately never used: Stage 10E only ever observes already-settled broker
facts, never an in-flight "accepted but not yet filled" state, so there is
no meaningful intermediate to park at)."""

_PRE_MATCH_STATUSES: frozenset[TradeStatus] = frozenset({TradeStatus.PENDING, TradeStatus.NOT_FILLED})
"""The only ``TradeStatus`` values Stage 10E ever assigns before a match:
``PENDING`` (still awaiting broker evidence) or ``NOT_FILLED`` (the
execution window closed with a confirmed-complete zero-candidate history
read - see ``MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED``)."""


class MT5TrackedRecommendation(MutableDomainModel):
    """Stage 10E's complete persisted per-recommendation tracking state.

    ``matched_position_id`` is set exactly once, on the cycle a match is
    first found, and is never changed afterward (see
    ``app.mt5.tracker.advance_tracked_recommendation``) - the structural
    invariant every restart/idempotency guarantee in Stage 10E rests on.
    """

    position_record: PositionRecord
    approved_broker_volume: Annotated[Decimal, Field(gt=0)]
    pre_existing_position_ids: tuple[int, ...] = ()
    matched_position_id: Annotated[int, Field(gt=0)] | None = None
    last_match_outcome: MT5MatchOutcome | None = None
    last_read_at: Timestamp | None = None

    @model_validator(mode="after")
    def _validate_pre_existing_ids_unique(self) -> Self:
        if len(set(self.pre_existing_position_ids)) != len(self.pre_existing_position_ids):
            raise ValueError("pre_existing_position_ids must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_matched_id_not_pre_existing(self) -> Self:
        if self.matched_position_id is not None and self.matched_position_id in self.pre_existing_position_ids:
            raise ValueError("matched_position_id must not be a pre-existing position id")
        return self

    @model_validator(mode="after")
    def _validate_status_matches_match_state(self) -> Self:
        if self.matched_position_id is not None:
            if self.position_record.status not in _POST_MATCH_STATUSES:
                raise ValueError("a matched recommendation must carry a post-match status")
        else:
            if self.position_record.status not in _PRE_MATCH_STATUSES:
                raise ValueError("an unmatched recommendation must carry a pre-match status")
        return self


class MT5PositionLifecycleAssessment(DomainModel):
    """Deterministic reconstruction of one matched broker ``position_id``'s
    complete lifecycle from its full deal history.

    ``READY`` requires every deal belonging to this ``position_id`` to have
    been safely classifiable (mirrors ``MT5RealizedDailyPnLAssessment``
    exactly) - including ``actual_entry``/``actual_entry_time`` (a matched
    position_id always has at least one qualifying ``IN`` deal; their
    absence under ``READY`` would itself be a logic inconsistency, not a
    legitimate business state). ``is_fully_closed`` distinguishes an ``OPEN``
    lifecycle (net volume still > 0, no terminal PnL) from a fully closed
    one (net volume == 0, ``realized_pnl`` is the terminal broker-booked
    result) - never both possible at once.
    """

    as_of: Timestamp
    position_id: Annotated[int, Field(gt=0)]
    outcome: MT5RealizedPnLOutcome
    is_fully_closed: bool | None = None
    actual_entry: Price | None = None
    actual_entry_time: Timestamp | None = None
    exit_price: Price | None = None
    exit_time: Timestamp | None = None
    realized_pnl: Decimal | None = None
    blocked_reasons: tuple[MT5RealizedPnLBlockReason, ...] = ()
    unsafe_deal_tickets: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _validate_ready_fields(self) -> Self:
        if self.outcome is MT5RealizedPnLOutcome.READY:
            if self.is_fully_closed is None:
                raise ValueError("READY requires is_fully_closed")
            if self.actual_entry is None or self.actual_entry_time is None:
                raise ValueError("READY requires actual_entry and actual_entry_time")
            if self.realized_pnl is None:
                raise ValueError("READY requires realized_pnl")
            if self.blocked_reasons:
                raise ValueError("READY must not carry blocked_reasons")
            if self.unsafe_deal_tickets:
                raise ValueError("READY must not carry unsafe_deal_tickets")
            if self.is_fully_closed:
                if self.exit_price is None or self.exit_time is None:
                    raise ValueError("a fully closed lifecycle requires exit_price and exit_time")
            else:
                if self.exit_price is not None or self.exit_time is not None:
                    raise ValueError("an open lifecycle must not carry exit_price/exit_time")
        else:
            if self.is_fully_closed is not None:
                raise ValueError("BLOCKED must not carry is_fully_closed")
            if self.actual_entry is not None or self.actual_entry_time is not None:
                raise ValueError("BLOCKED must not carry actual_entry/actual_entry_time")
            if self.exit_price is not None or self.exit_time is not None:
                raise ValueError("BLOCKED must not carry exit_price/exit_time")
            if self.realized_pnl is not None:
                raise ValueError("BLOCKED must not carry realized_pnl")
            if not self.blocked_reasons:
                raise ValueError("BLOCKED requires at least one blocked_reason")
            if not self.unsafe_deal_tickets:
                raise ValueError("BLOCKED requires at least one unsafe deal ticket")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_LIFECYCLE_REASON_ORDER.index(reason) for reason in self.blocked_reasons]
        if indexes != sorted(indexes):
            raise ValueError("blocked_reasons must be in canonical MT5RealizedPnLBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("blocked_reasons must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_unsafe_tickets_unique(self) -> Self:
        if len(set(self.unsafe_deal_tickets)) != len(self.unsafe_deal_tickets):
            raise ValueError("unsafe_deal_tickets must not contain duplicates")
        return self


__all__ = ["MT5PositionLifecycleAssessment", "MT5TrackedRecommendation"]
