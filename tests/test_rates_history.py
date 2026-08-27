"""Bounded, append-only rates/yields observation history (Stage 4B).

``(provider, provider_series_id, observation_time, revision_number)`` is the
*observation-revision* identity - not a unique ingestion-record identity:
the same revision may legitimately be observed more than once (an initially
valueless provider row, possibly re-polled, then its own first valued
observation). Semantic duplicate detection (below) is what keeps an
unchanged re-poll from consuming a new history slot merely because
``received_at`` differs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import GovernmentYieldType, PolicyRateKind, SeriesUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor
from app.rates.exceptions import DuplicateObservationError, RevisionConflictError
from app.rates.history import (
    DEFAULT_CAPACITY,
    GovernmentYieldObservationHistory,
    PolicyRateObservationHistory,
)


def _yield_obs(now: datetime, **overrides: object) -> GovernmentYieldObservation:
    fields: dict[str, object] = {
        "provider": "testrates",
        "provider_series_id": "us-10y-nominal",
        "country": "US",
        "currency": "USD",
        "yield_type": GovernmentYieldType.NOMINAL,
        "tenor": Tenor.of_years(10),
        "value": Decimal("4.10"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return GovernmentYieldObservation(**fields)


def _policy_obs(now: datetime, **overrides: object) -> PolicyRateObservation:
    fields: dict[str, object] = {
        "provider": "testrates",
        "provider_series_id": "fed-target-lower",
        "central_bank": CentralBank.FED,
        "currency": "USD",
        "rate_kind": PolicyRateKind.TARGET_LOWER,
        "value": Decimal("4.25"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return PolicyRateObservation(**fields)


# =====================================================================
# GovernmentYieldObservationHistory
# =====================================================================


def test_default_capacity_is_512() -> None:
    assert DEFAULT_CAPACITY == 512
    assert GovernmentYieldObservationHistory().capacity == 512


def test_capacity_is_configurable() -> None:
    history = GovernmentYieldObservationHistory(capacity=10)
    assert history.capacity == 10


def test_append_and_len(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    assert len(history) == 0
    history.append(_yield_obs(now))
    assert len(history) == 1


def test_bounded_eviction_is_deterministic_oldest_inserted_first(now: datetime) -> None:
    history = GovernmentYieldObservationHistory(capacity=2)
    a = _yield_obs(now, provider_series_id="a")
    b = _yield_obs(now, provider_series_id="b")
    c = _yield_obs(now, provider_series_id="c")
    history.append(a)
    history.append(b)
    history.append(c)
    assert history.dropped_count == 1
    assert len(history) == 2
    ids = {o.provider_series_id for o in history.all_observations()}
    assert ids == {"b", "c"}
    assert history.latest("testrates", "a") is None


def test_dropped_count_accumulates(now: datetime) -> None:
    history = GovernmentYieldObservationHistory(capacity=1)
    history.append(_yield_obs(now, provider_series_id="a"))
    history.append(_yield_obs(now, provider_series_id="b"))
    history.append(_yield_obs(now, provider_series_id="c"))
    assert history.dropped_count == 2


def test_provider_isolation(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    history.append(_yield_obs(now, provider="provider_a"))
    history.append(_yield_obs(now, provider="provider_b"))
    assert len(history.by_provider("provider_a")) == 1
    assert len(history.by_provider("provider_b")) == 1
    assert len(history.by_provider("provider_c")) == 0


def test_series_isolation_across_providers_with_colliding_series_id(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    a = _yield_obs(now, provider="provider_a", provider_series_id="shared-id")
    b = _yield_obs(now, provider="provider_b", provider_series_id="shared-id", value=Decimal("1"))
    history.append(a)
    history.append(b)  # must not raise despite identical provider_series_id
    assert len(history) == 2
    assert history.latest("provider_a", "shared-id") is not None
    assert history.latest("provider_b", "shared-id") is not None


def test_series_isolation_within_same_provider(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    two_year = _yield_obs(now, provider_series_id="us-2y-nominal", tenor=Tenor.of_years(2))
    ten_year = _yield_obs(now, provider_series_id="us-10y-nominal", tenor=Tenor.of_years(10))
    history.append(two_year)
    history.append(ten_year)
    assert len(history.observations_for("testrates", "us-2y-nominal")) == 1
    assert len(history.observations_for("testrates", "us-10y-nominal")) == 1


# --- Semantic duplicate detection (received_at excluded) --------------------


def test_repolled_with_only_received_at_changed_is_duplicate(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    original = _yield_obs(now)
    history.append(original)

    repoll = original.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateObservationError):
        history.append(repoll)


def test_rejected_semantic_duplicate_does_not_change_history_length(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    original = _yield_obs(now)
    history.append(original)

    repoll = original.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateObservationError):
        history.append(repoll)
    assert len(history) == 1


def test_rejected_semantic_duplicate_does_not_increment_dropped_count(now: datetime) -> None:
    history = GovernmentYieldObservationHistory(capacity=5)
    original = _yield_obs(now)
    history.append(original)

    repoll = original.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateObservationError):
        history.append(repoll)
    assert history.dropped_count == 0


def test_rejected_semantic_duplicate_does_not_alter_latest_lookup(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    original = _yield_obs(now)
    history.append(original)

    repoll = original.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateObservationError):
        history.append(repoll)
    latest = history.latest("testrates", "us-10y-nominal")
    assert latest is not None
    assert latest.received_at == now


# --- None -> valued progression, and conflict rules --------------------------


def test_none_to_valued_progression_is_allowed(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    unvalued = _yield_obs(now, value=None)
    history.append(unvalued)

    valued = unvalued.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.10")})
    history.append(valued)  # must not raise
    assert len(history) == 2


def test_valued_to_none_regression_raises_conflict(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    valued = _yield_obs(now, value=Decimal("4.10"))
    history.append(valued)

    regressed = valued.model_copy(update={"received_at": now + timedelta(hours=1), "value": None})
    with pytest.raises(RevisionConflictError):
        history.append(regressed)
    assert len(history) == 1


def test_same_revision_changed_value_raises_conflict(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    original = _yield_obs(now, value=Decimal("4.10"))
    history.append(original)

    conflicting = original.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.50")})
    with pytest.raises(RevisionConflictError):
        history.append(conflicting)
    assert len(history) == 1


def test_higher_revision_number_is_accepted_as_new_record(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    original = _yield_obs(now, value=Decimal("4.10"), revision_number=0)
    history.append(original)

    corrected = original.model_copy(
        update={"received_at": now + timedelta(days=1), "value": Decimal("4.15"), "revision_number": 1}
    )
    history.append(corrected)  # must not raise
    assert len(history) == 2
    latest = history.latest("testrates", "us-10y-nominal")
    assert latest is not None
    assert latest.revision_number == 1
    assert latest.value == Decimal("4.15")


def test_two_unvalued_observations_with_genuinely_different_content_are_both_retained(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    first = _yield_obs(now, value=None, source_url="https://a.example/1")
    second = first.model_copy(update={"received_at": now + timedelta(minutes=5), "source_url": "https://a.example/2"})
    history.append(first)
    history.append(second)  # must not raise
    assert len(history) == 2


def test_regression_is_rejected_even_when_content_matches_an_earlier_unvalued_observation(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    unvalued = _yield_obs(now, value=None)
    history.append(unvalued)

    valued = unvalued.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.10")})
    history.append(valued)

    # byte-identical to `unvalued` except received_at
    regressed = unvalued.model_copy(update={"received_at": now + timedelta(hours=2)})
    with pytest.raises(RevisionConflictError):
        history.append(regressed)
    assert len(history) == 2


# --- Ordering ------------------------------------------------------------


def test_all_observations_ordering_is_deterministic_by_observation_time(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    later = _yield_obs(now + timedelta(hours=1), provider_series_id="later")
    earlier = _yield_obs(now, provider_series_id="earlier")
    history.append(later)
    history.append(earlier)
    ordered_ids = [o.provider_series_id for o in history.all_observations()]
    assert ordered_ids == ["earlier", "later"]


def test_ordering_ties_broken_by_insertion_order(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    b = _yield_obs(now, provider_series_id="b")
    a = _yield_obs(now, provider_series_id="a")
    history.append(b)
    history.append(a)
    ordered_ids = [o.provider_series_id for o in history.all_observations()]
    assert ordered_ids == ["b", "a"]  # insertion order, NOT alphabetical


def test_ordering_is_not_based_on_received_at(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    earlier_market_time_ingested_later = _yield_obs(
        now, provider_series_id="a", received_at=now + timedelta(days=1)
    )
    later_market_time_ingested_first = _yield_obs(
        now + timedelta(hours=1), provider_series_id="b", received_at=now
    )
    history.append(later_market_time_ingested_first)
    history.append(earlier_market_time_ingested_later)
    ordered_ids = [o.provider_series_id for o in history.all_observations()]
    assert ordered_ids == ["a", "b"]


# --- latest() semantics ---------------------------------------------------


def test_latest_prefers_higher_observation_time_even_if_ingested_earlier(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    older_ingested_second = _yield_obs(now, value=Decimal("4.00"), received_at=now + timedelta(hours=2))
    newer_ingested_first = _yield_obs(now + timedelta(hours=1), value=Decimal("4.05"), received_at=now)
    history.append(newer_ingested_first)
    history.append(older_ingested_second)
    latest = history.latest("testrates", "us-10y-nominal")
    assert latest is not None
    assert latest.observation_time == now + timedelta(hours=1)
    assert latest.value == Decimal("4.05")


def test_latest_prefers_higher_revision_number_at_same_observation_time(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    revision_zero = _yield_obs(now, value=Decimal("4.00"), revision_number=0)
    history.append(revision_zero)
    revision_one = revision_zero.model_copy(
        update={"received_at": now + timedelta(days=1), "value": Decimal("4.05"), "revision_number": 1}
    )
    history.append(revision_one)
    latest = history.latest("testrates", "us-10y-nominal")
    assert latest is not None
    assert latest.revision_number == 1
    assert latest.value == Decimal("4.05")


def test_latest_prefers_most_recently_appended_within_same_exact_identity(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    unvalued = _yield_obs(now, value=None)
    history.append(unvalued)
    valued = unvalued.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.10")})
    history.append(valued)
    latest = history.latest("testrates", "us-10y-nominal")
    assert latest is not None
    assert latest.value == Decimal("4.10")


def test_latest_returns_none_when_never_seen() -> None:
    history = GovernmentYieldObservationHistory()
    assert history.latest("testrates", "unknown") is None


def test_historical_lookup_returns_all_revisions_in_order(now: datetime) -> None:
    history = GovernmentYieldObservationHistory()
    revision_zero = _yield_obs(now, value=Decimal("4.00"))
    history.append(revision_zero)
    revision_one = revision_zero.model_copy(
        update={"received_at": now + timedelta(days=1), "value": Decimal("4.05"), "revision_number": 1}
    )
    history.append(revision_one)
    revisions = history.observations_for("testrates", "us-10y-nominal")
    assert [r.value for r in revisions] == [Decimal("4.00"), Decimal("4.05")]


def test_equivalent_input_sequence_produces_identical_query_results(now: datetime) -> None:
    def build() -> GovernmentYieldObservationHistory:
        history = GovernmentYieldObservationHistory()
        unvalued = _yield_obs(now, value=None)
        history.append(unvalued)
        valued = unvalued.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.10")})
        history.append(valued)
        return history

    first = build()
    second = build()
    assert [o.model_dump() for o in first.all_observations()] == [o.model_dump() for o in second.all_observations()]
    latest_first = first.latest("testrates", "us-10y-nominal")
    latest_second = second.latest("testrates", "us-10y-nominal")
    assert latest_first is not None and latest_second is not None
    assert latest_first.model_dump() == latest_second.model_dump()


# =====================================================================
# PolicyRateObservationHistory - same append/duplicate/conflict/ordering
# rules, verified independently since it is a separate concrete class.
# =====================================================================


def test_policy_rate_default_capacity_is_512() -> None:
    assert PolicyRateObservationHistory().capacity == 512


def test_policy_rate_capacity_is_configurable() -> None:
    assert PolicyRateObservationHistory(capacity=7).capacity == 7


def test_policy_rate_append_and_len(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    history.append(_policy_obs(now))
    assert len(history) == 1


def test_policy_rate_bounded_eviction_is_deterministic(now: datetime) -> None:
    history = PolicyRateObservationHistory(capacity=2)
    history.append(_policy_obs(now, provider_series_id="a"))
    history.append(_policy_obs(now, provider_series_id="b"))
    history.append(_policy_obs(now, provider_series_id="c"))
    assert history.dropped_count == 1
    assert len(history) == 2
    assert {o.provider_series_id for o in history.all_observations()} == {"b", "c"}


def test_policy_rate_dropped_count_accumulates(now: datetime) -> None:
    history = PolicyRateObservationHistory(capacity=1)
    history.append(_policy_obs(now, provider_series_id="a"))
    history.append(_policy_obs(now, provider_series_id="b"))
    history.append(_policy_obs(now, provider_series_id="c"))
    assert history.dropped_count == 2


def test_policy_rate_provider_isolation(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    history.append(_policy_obs(now, provider="provider_a"))
    history.append(_policy_obs(now, provider="provider_b"))
    assert len(history.by_provider("provider_a")) == 1
    assert len(history.by_provider("provider_b")) == 1


def test_policy_rate_target_lower_and_upper_are_isolated_series(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    lower = _policy_obs(
        now, provider_series_id="fed-target-lower", rate_kind=PolicyRateKind.TARGET_LOWER, value=Decimal("4.25")
    )
    upper = _policy_obs(
        now, provider_series_id="fed-target-upper", rate_kind=PolicyRateKind.TARGET_UPPER, value=Decimal("4.50")
    )
    history.append(lower)
    history.append(upper)
    latest_lower = history.latest("testrates", "fed-target-lower")
    latest_upper = history.latest("testrates", "fed-target-upper")
    assert latest_lower is not None and latest_lower.value == Decimal("4.25")
    assert latest_upper is not None and latest_upper.value == Decimal("4.50")


def test_policy_rate_repolled_with_only_received_at_changed_is_duplicate(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    original = _policy_obs(now)
    history.append(original)
    repoll = original.model_copy(update={"received_at": now + timedelta(minutes=10)})
    with pytest.raises(DuplicateObservationError):
        history.append(repoll)
    assert len(history) == 1
    assert history.dropped_count == 0


def test_policy_rate_none_to_valued_progression_is_allowed(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    unvalued = _policy_obs(now, value=None)
    history.append(unvalued)
    valued = unvalued.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.25")})
    history.append(valued)
    assert len(history) == 2
    latest = history.latest("testrates", "fed-target-lower")
    assert latest is not None and latest.value == Decimal("4.25")


def test_policy_rate_valued_to_none_regression_raises_conflict(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    valued = _policy_obs(now, value=Decimal("4.25"))
    history.append(valued)
    regressed = valued.model_copy(update={"received_at": now + timedelta(hours=1), "value": None})
    with pytest.raises(RevisionConflictError):
        history.append(regressed)
    assert len(history) == 1


def test_policy_rate_same_revision_changed_value_raises_conflict(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    original = _policy_obs(now, value=Decimal("4.25"))
    history.append(original)
    conflicting = original.model_copy(update={"received_at": now + timedelta(hours=1), "value": Decimal("4.50")})
    with pytest.raises(RevisionConflictError):
        history.append(conflicting)
    assert len(history) == 1


def test_policy_rate_higher_revision_number_is_accepted(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    original = _policy_obs(now, value=Decimal("4.25"), revision_number=0)
    history.append(original)
    corrected = original.model_copy(
        update={"received_at": now + timedelta(days=1), "value": Decimal("4.30"), "revision_number": 1}
    )
    history.append(corrected)
    latest = history.latest("testrates", "fed-target-lower")
    assert latest is not None
    assert latest.revision_number == 1
    assert latest.value == Decimal("4.30")


def test_policy_rate_latest_returns_none_when_never_seen() -> None:
    assert PolicyRateObservationHistory().latest("testrates", "unknown") is None


def test_policy_rate_historical_lookup_returns_all_revisions_in_order(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    revision_zero = _policy_obs(now, value=Decimal("4.25"))
    history.append(revision_zero)
    revision_one = revision_zero.model_copy(
        update={"received_at": now + timedelta(days=1), "value": Decimal("4.30"), "revision_number": 1}
    )
    history.append(revision_one)
    revisions = history.observations_for("testrates", "fed-target-lower")
    assert [r.value for r in revisions] == [Decimal("4.25"), Decimal("4.30")]


def test_policy_rate_ordering_ties_broken_by_insertion_order(now: datetime) -> None:
    history = PolicyRateObservationHistory()
    b = _policy_obs(now, provider_series_id="b")
    a = _policy_obs(now, provider_series_id="a")
    history.append(b)
    history.append(a)
    assert [o.provider_series_id for o in history.all_observations()] == ["b", "a"]
