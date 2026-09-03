"""Stage 10E pure recommendation <-> broker deal matching.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock, never generates a random/UUID identity - a deterministic,
synchronous function of its explicit arguments only. Mirrors ``app.mt5.risk``/
``app.mt5.history`` one architectural layer over: expected matching states
are typed return values, never exceptions, and an unsafe/ambiguous input
never silently resolves to a fabricated single winner.

Matching operates at the broker *position lifecycle* level (``position_id``),
never at one individual deal in isolation: a broker may split one approved
order into several entry fills sharing the same ``position_id`` (a stop-loss
hunt, partial liquidity, or simply the broker's own execution behavior), so
the exact-volume safety rule (never invent a tolerance - see the approved
Stage 10E design) is enforced against a ``position_id``'s *total* qualifying
opening volume, never against one deal's ``volume`` field alone.

The impure boundary (a future runtime orchestration layer, and
``app.mt5.client``) is responsible for gathering ``deals``/
``history_read_status``/``history_covers_until`` and every recommendation-
side fact - this module never gathers any of them itself, and never re-runs
once a recommendation is already ``MATCHED`` (see ``app.mt5.tracker.
advance_tracked_recommendation``, the sole caller that enforces match
immutability - ``PARTIAL_FILL``/``VOLUME_MISMATCH``/``AMBIGUOUS``/
``NO_CANDIDATE_YET``/``READ_UNAVAILABLE`` are all non-terminal from the
tracker's perspective and simply cause matching to be attempted again next
cycle).
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.enums.mt5_matching import MT5MatchOutcome
from app.core.enums.trade import TradeDirection
from app.core.models.base import Symbol, Timestamp
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_matching import MT5MatchResult
from app.mt5.history import MT5HistoryReadStatus

_DIRECTION_TO_DEAL_TYPE: dict[TradeDirection, MT5DealType] = {
    TradeDirection.LONG: MT5DealType.BUY,
    TradeDirection.SHORT: MT5DealType.SELL,
}
"""``NEUTRAL``/``WAIT`` intentionally absent: no broker deal type could ever
match them, so any recommendation carrying one simply matches zero
candidates - no explicit rejection branch is needed."""


def _qualifies_structurally(
    deal: MT5Deal,
    *,
    symbol: Symbol,
    expected_deal_type: MT5DealType | None,
    signal_time: Timestamp,
    valid_until: Timestamp,
    pre_existing_position_ids: tuple[int, ...],
    already_claimed_position_ids: tuple[int, ...],
) -> bool:
    """Every hard constraint except the volume total (which can only be
    evaluated once a ``position_id``'s qualifying fills are grouped - see
    ``match_recommendation``)."""
    if expected_deal_type is None:
        return False
    if deal.deal_type is not expected_deal_type:
        return False
    if deal.entry is not MT5DealEntry.IN:
        return False
    if deal.symbol != symbol:
        return False
    if not (signal_time <= deal.time <= valid_until):
        return False
    if deal.position_id in pre_existing_position_ids:
        return False
    if deal.position_id in already_claimed_position_ids:
        return False
    return True


def _is_first_lifecycle_consistent(position_id: int, group: list[MT5Deal], deals: tuple[MT5Deal, ...]) -> bool:
    """Consistency check: every deal in ``group`` (this ``position_id``'s
    qualifying opening fills) must, together, contain the earliest deal on
    record for that ``position_id`` across the *entire* supplied history -
    defense-in-depth on top of the caller-confirmed ``pre_existing_
    position_ids`` snapshot, never the primary source of truth for
    pre-existing-exposure protection. Applied once per group (never per
    individual deal): a later fill of a genuinely fresh multi-fill open is
    not penalized merely for not itself being the earliest deal, as long as
    the group's own earliest member is the position's true genesis deal."""
    earliest_any = min(deal.time for deal in deals if deal.position_id == position_id)
    earliest_in_group = min(deal.time for deal in group)
    return earliest_any == earliest_in_group


def match_recommendation(
    *,
    as_of: Timestamp,
    symbol: Symbol,
    direction: TradeDirection,
    signal_time: Timestamp,
    valid_until: Timestamp,
    approved_broker_volume: Decimal,
    pre_existing_position_ids: tuple[int, ...],
    already_claimed_position_ids: tuple[int, ...],
    deals: tuple[MT5Deal, ...],
    history_read_status: MT5HistoryReadStatus,
    history_covers_until: Timestamp,
) -> MT5MatchResult:
    """One deterministic matching attempt.

    ``history_covers_until`` is the caller's explicit claim about how far a
    confirmed-``"OK"`` read actually reached - never assumed to be ``as_of``
    or inferred from ``deals`` itself, so a stale-but-technically-``"OK"``
    read can never be mistaken for one that covers the complete validity
    window. Price is deliberately not consulted anywhere here (approved V1
    Option A - see the Stage 10E design report): it is never a matching
    constraint, only ever an evidence fact a caller may inspect separately
    on the winning ``MT5Deal.price``.

    Ownership, not volume shape, is the first question: every ``position_id``
    whose qualifying opening fills pass every hard constraint (symbol,
    direction, window, pre-existing/already-claimed exclusion, first-
    lifecycle consistency) is a *structurally eligible lifecycle* - a broker
    position this recommendation could plausibly own - regardless of whether
    its total volume happens to equal, undershoot, or overshoot
    ``approved_broker_volume``. V1 has no ranking/scoring/heuristic winner
    (see the approved Stage 10E design), so volume shape may never be used
    to prefer one eligible lifecycle over another: two or more structurally
    eligible ``position_id``s - in any combination of full/partial/overfilled
    volume - is unresolved ownership, always ``AMBIGUOUS``, carrying every
    such ``position_id`` (not just the exact-volume ones) in
    ``candidate_position_ids``. Only once exactly one structurally eligible
    lifecycle remains does its volume classify the outcome: exactly
    ``approved_broker_volume`` -> ``MATCHED``; strictly less -> ``PARTIAL_FILL``;
    strictly more -> ``VOLUME_MISMATCH``. With zero structurally eligible
    lifecycles, the original zero-candidate timing semantics
    (``NO_CANDIDATE_YET``/``EXPIRED_CONFIRMED_UNFILLED``) apply.
    """
    if history_read_status != "OK":
        return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.READ_UNAVAILABLE)

    expected_deal_type = _DIRECTION_TO_DEAL_TYPE.get(direction)
    groups: dict[int, list[MT5Deal]] = {}
    for deal in deals:
        if _qualifies_structurally(
            deal,
            symbol=symbol,
            expected_deal_type=expected_deal_type,
            signal_time=signal_time,
            valid_until=valid_until,
            pre_existing_position_ids=pre_existing_position_ids,
            already_claimed_position_ids=already_claimed_position_ids,
        ):
            groups.setdefault(deal.position_id, []).append(deal)

    eligible_position_ids = sorted(
        position_id for position_id, group in groups.items() if _is_first_lifecycle_consistent(position_id, group, deals)
    )

    if len(eligible_position_ids) >= 2:
        return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.AMBIGUOUS, candidate_position_ids=tuple(eligible_position_ids))

    if len(eligible_position_ids) == 1:
        position_id = eligible_position_ids[0]
        total_opening_volume = sum((deal.volume for deal in groups[position_id]), Decimal("0"))
        if total_opening_volume == approved_broker_volume:
            return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.MATCHED, matched_position_id=position_id)
        if total_opening_volume < approved_broker_volume:
            return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.PARTIAL_FILL, candidate_position_ids=(position_id,))
        return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.VOLUME_MISMATCH, candidate_position_ids=(position_id,))

    if history_covers_until >= valid_until:
        return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED)

    return MT5MatchResult(as_of=as_of, outcome=MT5MatchOutcome.NO_CANDIDATE_YET)


__all__ = ["match_recommendation"]
