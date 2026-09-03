"""Stage 10B pure rollover-state transition logic.

Never imports ``MetaTrader5``, never touches the filesystem, never reads the
system clock - every function here is a deterministic, synchronous function
of its explicit arguments only (``as_of``, current equity/PnL, the caller-
supplied persisted-state read outcome, and ``MT5RolloverPolicyConfig``).
Mirrors ``app.risk.engine``/``app.statistics.session`` one architectural
layer over: expected persistence/rollover states are typed return values,
never exceptions.

The impure boundary (``app.mt5.persistence.MT5RolloverStatePersistence``,
and whatever future caller obtains ``datetime.now(UTC)`` and MT5 account
facts) is responsible for gathering ``current_equity``, ``floating_pnl``,
``as_of`` and the persisted-state read outcome, then handing them to
``decide_rollover``/``build_rollover_snapshot`` - this module never gathers
any of them itself.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.mt5_rollover import MT5RolloverEstablishmentMode, MT5RolloverOutcome
from app.core.models.base import Timestamp
from app.core.models.mt5_rollover import MT5RolloverSnapshot, MT5RolloverState

PersistedStateReadStatus = Literal["ABSENT", "VALID", "CORRUPT", "UNAVAILABLE"]
"""What ``MT5RolloverStatePersistence.read()`` observed, handed to
``decide_rollover`` alongside the state itself (present only for
``"VALID"``). Defined here (the pure module) rather than in the impure
``app.mt5.persistence`` so this module never depends on its own impure
counterpart - ``persistence.py`` imports this alias instead."""

RolloverProgressionClass = Literal["USABLE_FOR_FUTURE_ACCOUNT_RISK_ASSEMBLY", "BLOCK_RUNTIME_CYCLE"]
"""Coarse downstream classification of an ``MT5RolloverOutcome``. Never a
claim that Stage 7/8/9 was invoked - Stage 10B invokes nothing downstream;
this only tells a future caller whether the produced ``MT5RolloverSnapshot``
may eventually participate in a later ``AccountRiskSnapshot`` assembly."""

_USABLE_OUTCOMES: frozenset[MT5RolloverOutcome] = frozenset(
    {MT5RolloverOutcome.READY, MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY}
)
"""A locally-owned copy of the usable-outcome set - not imported from
``app.core.models.mt5_rollover`` (whose own model validator independently
re-derives the identical membership to self-validate ``MT5RolloverSnapshot``),
mirroring the Stage 5A/6A/6C/7/8/9 precedent of the operational component and
the result model's self-validation maintaining independent copies of the
same primitive rather than cross-importing one from the other."""


def compute_trading_day_key(as_of: Timestamp, policy: MT5RolloverPolicyConfig) -> str:
    """Broker-local calendar date (``YYYY-MM-DD``) at the configured
    rollover boundary. DST-safe: ``zoneinfo``-aware arithmetic normalizes
    correctly across transitions, unlike naive/``pytz``-style offset math."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    broker_local = as_of.astimezone(ZoneInfo(policy.rollover_timezone))
    shifted = broker_local - timedelta(hours=policy.rollover_hour)
    return shifted.date().isoformat()


def trading_day_interval(trading_day_key: str, policy: MT5RolloverPolicyConfig) -> tuple[Timestamp, Timestamp]:
    """The canonical inverse/boundary companion to
    ``compute_trading_day_key``: the half-open ``[start, end)`` broker-local
    interval for one trading day, both aware datetimes. ``start`` is the
    exact rollover-boundary instant that keys onto ``trading_day_key`` via
    ``compute_trading_day_key``; ``end`` is the same wall-clock instant one
    calendar day later. Uses the identical ``zoneinfo``-aware arithmetic as
    ``compute_trading_day_key`` itself (never naive/offset math), so the two
    functions stay DST-consistent by construction: whatever wall-clock
    transition ``compute_trading_day_key`` experiences on a given date,
    ``trading_day_interval`` experiences the same transition when computing
    ``end`` for the calendar day before it.

    A future caller (e.g. a Stage 10D deal-history read) must derive this
    interval here rather than re-deriving broker-trading-day boundary math
    itself - this module remains the sole owner of that policy.
    """
    calendar_date = date.fromisoformat(trading_day_key)
    tz = ZoneInfo(policy.rollover_timezone)
    start = datetime(calendar_date.year, calendar_date.month, calendar_date.day, policy.rollover_hour, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def decide_rollover(
    *,
    current_trading_day_key: str,
    current_equity: Decimal,
    as_of: Timestamp,
    policy: MT5RolloverPolicyConfig,
    persisted_read_status: PersistedStateReadStatus,
    persisted_state: MT5RolloverState | None,
) -> tuple[MT5RolloverOutcome, MT5RolloverState | None]:
    """The six-case deterministic rollover state machine.

    ``persisted_state`` must be non-``None`` if and only if
    ``persisted_read_status == "VALID"`` - the caller (impure persistence
    layer) guarantees this pairing; this function asserts it rather than
    silently tolerating a mismatched pair.
    """
    if persisted_read_status == "CORRUPT":
        return MT5RolloverOutcome.PERSISTENCE_CORRUPT, None
    if persisted_read_status == "UNAVAILABLE":
        return MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE, None

    if persisted_read_status == "ABSENT":
        bootstrapped = MT5RolloverState(
            trading_day_key=current_trading_day_key,
            rollover_equity=current_equity,
            established_at=as_of,
            rollover_timezone=policy.rollover_timezone,
            rollover_hour=policy.rollover_hour,
            establishment_mode=MT5RolloverEstablishmentMode.MIDDAY_BOOTSTRAP,
        )
        return MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY, bootstrapped

    assert persisted_state is not None  # guaranteed by persisted_read_status == "VALID"

    if current_trading_day_key < persisted_state.trading_day_key:
        return MT5RolloverOutcome.FUTURE_STATE, None

    if current_trading_day_key > persisted_state.trading_day_key:
        new_day_state = MT5RolloverState(
            trading_day_key=current_trading_day_key,
            rollover_equity=current_equity,
            established_at=as_of,
            rollover_timezone=policy.rollover_timezone,
            rollover_hour=policy.rollover_hour,
            establishment_mode=MT5RolloverEstablishmentMode.POST_BOUNDARY_FIRST_OBSERVATION,
        )
        return MT5RolloverOutcome.READY, new_day_state

    # Same trading_day_key: reuse persisted equity unless the policy that
    # produced it has since changed underneath it.
    if persisted_state.rollover_timezone != policy.rollover_timezone or persisted_state.rollover_hour != policy.rollover_hour:
        return MT5RolloverOutcome.CONFIG_MISMATCH, None

    return MT5RolloverOutcome.READY, persisted_state


def build_rollover_snapshot(
    *,
    as_of: Timestamp,
    current_equity: Decimal,
    floating_pnl: Decimal,
    outcome: MT5RolloverOutcome,
    rollover_state: MT5RolloverState | None,
) -> MT5RolloverSnapshot:
    """Assemble Stage 10B's deliverable from an already-decided outcome."""
    return MT5RolloverSnapshot(
        as_of=as_of,
        rollover_outcome=outcome,
        rollover_state=rollover_state,
        current_equity=current_equity,
        floating_pnl=floating_pnl,
    )


def classify_rollover_outcome(outcome: MT5RolloverOutcome) -> RolloverProgressionClass:
    """Whether a future caller may eventually use this outcome toward
    ``AccountRiskSnapshot`` assembly - never an invocation of Stage 7/8/9."""
    return "USABLE_FOR_FUTURE_ACCOUNT_RISK_ASSEMBLY" if outcome in _USABLE_OUTCOMES else "BLOCK_RUNTIME_CYCLE"


__all__ = [
    "PersistedStateReadStatus",
    "RolloverProgressionClass",
    "build_rollover_snapshot",
    "classify_rollover_outcome",
    "compute_trading_day_key",
    "decide_rollover",
    "trading_day_interval",
]
