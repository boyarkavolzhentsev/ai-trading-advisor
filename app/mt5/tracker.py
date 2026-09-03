"""Stage 10E pure recommendation lifecycle tracking.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock, never generates a random/UUID identity - a deterministic,
synchronous function of its explicit arguments only. Never invokes
``StatisticsAggregator`` or ``RiskGate`` - both remain downstream consumers
of the ``PositionRecord`` this module produces/updates, never callees of it.

Three responsibilities, composed from narrowest to broadest:

``reconstruct_position_lifecycle`` - given one broker ``position_id`` and its
complete deal history, deterministically derive entry/exit aggregation and
terminal PnL, reusing ``app.mt5.history.classify_trading_deal`` exactly (never
a second, conflicting financial formula).

``create_tracked_recommendation`` - the narrow pure factory building a fresh
``MT5TrackedRecommendation`` at recommendation-issuance time. Takes a
caller-supplied, already-read ``positions()`` snapshot and its status
verbatim - never touches ``app.mt5.client`` itself, never fabricates a
confirmed-empty pre-existing-position set from an unsafe read.

``advance_tracked_recommendation`` - the single per-cycle driver, and the
sole place match immutability (Stage 10E's central invariant) is enforced:
once ``matched_position_id`` is set it is never re-derived, only ever reused
to drive lifecycle reconstruction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.enums.market import MarketType
from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.enums.mt5_matching import MT5MatchOutcome, MT5TrackedRecommendationCreationOutcome
from app.core.enums.trade import TradeDirection, TradeStatus
from app.core.models.base import Price, Symbol, Timestamp
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_matching import MT5TrackedRecommendationCreationResult
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_tracking import MT5PositionLifecycleAssessment, MT5TrackedRecommendation
from app.core.models.position import PositionRecord
from app.mt5.history import MT5HistoryReadStatus, classify_trading_deal
from app.mt5.matching import match_recommendation
from app.mt5.risk import MT5PositionsReadStatus

_LIFECYCLE_REASON_ORDER: tuple[MT5RealizedPnLBlockReason, ...] = tuple(MT5RealizedPnLBlockReason)
"""A locally-owned copy of the canonical reason order - mirrors ``app.mt5.
history``'s own identical precedent one file over."""

_EPOCH: Timestamp = datetime(1970, 1, 1, tzinfo=UTC)
"""Mirrors ``app.mt5.history``'s identical epoch-sentinel check - a deal
whose normalized ``time`` is at or before it is MT5's own "unset" sentinel
having survived normalization, never a genuine historical fact."""


def _with_updates(model: Any, **overrides: object) -> Any:
    """Construct a new, fully re-validated instance of ``model``'s class
    with ``overrides`` applied - never a bare attribute assignment (which
    would re-run cross-field ``MutableDomainModel`` validators against a
    transient, possibly-invalid intermediate state whenever more than one
    field must change together) and never an unvalidated ``model_copy``."""
    return type(model)(**{**model.model_dump(), **overrides})


def reconstruct_position_lifecycle(
    *, position_id: int, deals: tuple[MT5Deal, ...], as_of: Timestamp
) -> MT5PositionLifecycleAssessment:
    """Deterministic reconstruction of one matched ``position_id``'s
    complete lifecycle from its full deal history.

    Caller contract: ``deals`` must include this ``position_id``'s complete
    history back to its genesis ``IN`` deal on every call - never only the
    deals newly observed since the last poll. In practice this means the
    caller always queries ``history_deals(start=signal_time, end=now)``
    (or earlier), never a narrower incremental window; this is what makes
    every call idempotent (same complete input -> same output) rather than
    stateful. A ``position_id`` with zero qualifying ``IN`` deals in the
    supplied history is a caller-contract violation, not a legitimate
    business state - see the ``assert`` below.

    Filters ``deals`` to this ``position_id`` internally (never trusts the
    caller to have pre-filtered) and reuses ``classify_trading_deal``
    per-deal, exactly as ``app.mt5.history.compute_realized_daily_pnl``
    does for its own (differently-scoped) aggregation - the same fail-closed
    philosophy applies: any single unsafe deal blocks the whole assessment,
    no partial reconstruction is ever produced.
    """
    relevant = tuple(deal for deal in deals if deal.position_id == position_id)

    blocked_reason_set: set[MT5RealizedPnLBlockReason] = set()
    unsafe_tickets: list[int] = []
    contributions: list[Decimal] = []
    in_deals: list[MT5Deal] = []
    out_deals: list[MT5Deal] = []
    net_volume = Decimal("0")

    for deal in relevant:
        if deal.time <= _EPOCH:
            blocked_reason_set.add(MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP)
            unsafe_tickets.append(deal.ticket)
            continue

        if deal.deal_type is MT5DealType.NON_TRADING:
            continue

        if deal.deal_type is MT5DealType.UNKNOWN:
            blocked_reason_set.add(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE)
            unsafe_tickets.append(deal.ticket)
            continue

        contribution, reason = classify_trading_deal(deal)
        if reason is not None:
            blocked_reason_set.add(reason)
            unsafe_tickets.append(deal.ticket)
            continue

        contributions.append(contribution)
        if deal.entry is MT5DealEntry.IN:
            net_volume += deal.volume
            in_deals.append(deal)
        else:
            net_volume -= deal.volume
            out_deals.append(deal)

    if blocked_reason_set:
        reasons = tuple(reason for reason in _LIFECYCLE_REASON_ORDER if reason in blocked_reason_set)
        return MT5PositionLifecycleAssessment(
            as_of=as_of,
            position_id=position_id,
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=reasons,
            unsafe_deal_tickets=tuple(unsafe_tickets),
        )

    assert in_deals, "a matched position_id is guaranteed at least one qualifying IN deal by match_recommendation"

    entry_volume = sum((deal.volume for deal in in_deals), Decimal("0"))
    actual_entry = sum((deal.price * deal.volume for deal in in_deals), Decimal("0")) / entry_volume
    actual_entry_time = min(deal.time for deal in in_deals)
    realized_pnl = sum(contributions, Decimal("0"))
    is_fully_closed = net_volume <= Decimal("0")

    exit_price: Price | None = None
    exit_time: Timestamp | None = None
    if is_fully_closed:
        assert out_deals, "net volume cannot reach zero without at least one closing deal"
        exit_volume = sum((deal.volume for deal in out_deals), Decimal("0"))
        exit_price = sum((deal.price * deal.volume for deal in out_deals), Decimal("0")) / exit_volume
        exit_time = max(deal.time for deal in out_deals)

    return MT5PositionLifecycleAssessment(
        as_of=as_of,
        position_id=position_id,
        outcome=MT5RealizedPnLOutcome.READY,
        is_fully_closed=is_fully_closed,
        actual_entry=actual_entry,
        actual_entry_time=actual_entry_time,
        exit_price=exit_price,
        exit_time=exit_time,
        realized_pnl=realized_pnl,
    )


def create_tracked_recommendation(
    *,
    as_of: Timestamp,
    trade_id: str,
    symbol: Symbol,
    market: MarketType,
    direction: TradeDirection,
    signal_time: Timestamp,
    valid_until: Timestamp,
    planned_entry: Price,
    stop_loss: Price,
    take_profit_levels: tuple[Price, ...] = (),
    approved_broker_volume: Decimal,
    pre_existing_positions_read_status: MT5PositionsReadStatus,
    pre_existing_positions: tuple[MT5Position, ...],
) -> MT5TrackedRecommendationCreationResult:
    """The narrow pure factory: builds a fresh ``MT5TrackedRecommendation``
    (embedding a fresh ``PENDING`` ``PositionRecord``) only when the caller-
    supplied ``positions()`` snapshot was itself confirmed safe.

    ``pre_existing_positions`` is expected already filtered to ``symbol`` by
    the caller (or not - this function filters again itself, exactly like
    every other Stage 10 pure aggregator never trusts a caller's own
    pre-filtering). Never calls ``app.mt5.client`` - the snapshot is always
    an explicit, already-read argument.
    """
    if pre_existing_positions_read_status != "OK":
        return MT5TrackedRecommendationCreationResult(
            as_of=as_of, outcome=MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE
        )

    pre_existing_position_ids = tuple(sorted({position.ticket for position in pre_existing_positions if position.symbol == symbol}))

    position_record = PositionRecord(
        trade_id=trade_id,
        symbol=symbol,
        market=market,
        direction=direction,
        signal_time=signal_time,
        valid_until=valid_until,
        status=TradeStatus.PENDING,
        planned_entry=planned_entry,
        stop_loss=stop_loss,
        take_profit_levels=list(take_profit_levels),
    )
    tracked = MT5TrackedRecommendation(
        position_record=position_record,
        approved_broker_volume=approved_broker_volume,
        pre_existing_position_ids=pre_existing_position_ids,
    )
    return MT5TrackedRecommendationCreationResult(
        as_of=as_of, outcome=MT5TrackedRecommendationCreationOutcome.CREATED, tracked_recommendation=tracked
    )


def _classify_terminal_status(pnl: Decimal) -> TradeStatus:
    if pnl > 0:
        return TradeStatus.WIN
    if pnl < 0:
        return TradeStatus.LOSS
    return TradeStatus.BREAKEVEN


def advance_tracked_recommendation(
    *,
    as_of: Timestamp,
    tracked: MT5TrackedRecommendation,
    deals: tuple[MT5Deal, ...],
    history_read_status: MT5HistoryReadStatus,
    history_covers_until: Timestamp,
    already_claimed_position_ids: tuple[int, ...],
) -> MT5TrackedRecommendation:
    """The single per-cycle poll entry point and the sole enforcer of match
    immutability: matching is attempted if and only if
    ``tracked.matched_position_id is None``; once set, every later call
    skips straight to lifecycle reconstruction for that exact
    ``position_id`` - it is structurally impossible for this function to
    ever re-match or re-assign a different broker lifecycle to an already-
    matched recommendation.
    """
    if tracked.matched_position_id is None:
        match_result = match_recommendation(
            as_of=as_of,
            symbol=tracked.position_record.symbol,
            direction=tracked.position_record.direction,
            signal_time=tracked.position_record.signal_time,
            valid_until=tracked.position_record.valid_until,
            approved_broker_volume=tracked.approved_broker_volume,
            pre_existing_position_ids=tracked.pre_existing_position_ids,
            already_claimed_position_ids=already_claimed_position_ids,
            deals=deals,
            history_read_status=history_read_status,
            history_covers_until=history_covers_until,
        )

        if match_result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED:
            updated_record = _with_updates(tracked.position_record, status=TradeStatus.NOT_FILLED)
            return _with_updates(
                tracked, position_record=updated_record, last_match_outcome=match_result.outcome, last_read_at=as_of
            )

        if match_result.outcome is not MT5MatchOutcome.MATCHED:
            return _with_updates(tracked, last_match_outcome=match_result.outcome, last_read_at=as_of)

        assert match_result.matched_position_id is not None
        # A MATCHED position_id always has >=1 qualifying deal within `deals`
        # (the very deal match_recommendation found it from) - lifecycle
        # reconstruction below proceeds in the same cycle using the same
        # deals, never a second, later read.
        tracked = _with_updates(
            tracked,
            matched_position_id=match_result.matched_position_id,
            last_match_outcome=match_result.outcome,
            last_read_at=as_of,
            position_record=_with_updates(tracked.position_record, status=TradeStatus.OPEN),
        )

    assert tracked.matched_position_id is not None

    if history_read_status != "OK":
        return _with_updates(tracked, last_read_at=as_of)

    lifecycle = reconstruct_position_lifecycle(position_id=tracked.matched_position_id, deals=deals, as_of=as_of)
    if lifecycle.outcome is not MT5RealizedPnLOutcome.READY:
        return _with_updates(tracked, last_read_at=as_of)

    if not lifecycle.is_fully_closed:
        updated_record = _with_updates(
            tracked.position_record,
            status=TradeStatus.OPEN,
            actual_entry=lifecycle.actual_entry,
            actual_entry_time=lifecycle.actual_entry_time,
        )
        return _with_updates(tracked, position_record=updated_record, last_read_at=as_of)

    assert lifecycle.realized_pnl is not None
    assert lifecycle.exit_price is not None
    assert lifecycle.exit_time is not None
    updated_record = _with_updates(
        tracked.position_record,
        status=_classify_terminal_status(lifecycle.realized_pnl),
        actual_entry=lifecycle.actual_entry,
        actual_entry_time=lifecycle.actual_entry_time,
        exit_price=lifecycle.exit_price,
        exit_time=lifecycle.exit_time,
        pnl=lifecycle.realized_pnl,
    )
    return _with_updates(tracked, position_record=updated_record, last_read_at=as_of)


__all__ = ["advance_tracked_recommendation", "create_tracked_recommendation", "reconstruct_position_lifecycle"]
