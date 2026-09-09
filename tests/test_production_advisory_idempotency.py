"""Stage 0D duplicate-cycle / idempotency preflight tests (Retry /
Idempotency Design Closure).

The preflight runs entirely inside ``ProductionAdvisoryComposer.run_cycle``'s
lock, before ``run_runtime_cycle`` is ever called - every test here proves
that boundary directly by monkeypatching ``run_runtime_cycle`` and asserting
it was (or was not) invoked.
"""

from __future__ import annotations

import asyncio

import pytest

import app.production_advisory.composer as composer_module
from app.core.enums.strategy_router import StrategyFamily
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError
from tests.production_advisory_support import AS_OF, FakeFlowBootstrap, FakeMT5Client, FakeRecordPersistence, all_trade_ids, build_config


def _make_composer(*, tracking=None, provenance=None) -> tuple[ProductionAdvisoryComposer, FakeRecordPersistence, FakeRecordPersistence]:
    tracking = tracking if tracking is not None else FakeRecordPersistence()
    provenance = provenance if provenance is not None else FakeRecordPersistence()
    composer = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=FakeFlowBootstrap(),
        mt5_client=FakeMT5Client(),
        tracking_persistence=tracking,
        provenance_persistence=provenance,
    )
    return composer, tracking, provenance


def _fake_run_runtime_cycle(monkeypatch: pytest.MonkeyPatch):
    """``run_runtime_cycle`` is synchronous in production; this fake stays
    synchronous too - every test that needs a genuine "still in flight"
    window uses ``asyncio.gather`` over two real ``run_cycle`` coroutines
    instead of an artificial delay inside this fake."""
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object):
        calls.append(kwargs)
        from datetime import UTC, datetime

        from app.core.enums.mt5_runtime import MT5ConnectivityState
        from app.core.enums.runtime_cycle import RuntimeCycleOutcome
        from app.core.models.mt5_runtime import MT5RuntimeStatus
        from app.core.models.runtime_cycle import RuntimeCycleResult

        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome.BLOCKED,
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.TERMINAL_UNAVAILABLE),
        )

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake)
    return calls


# --- first-call / basic duplicate detection ---------------------------------


@pytest.mark.asyncio
async def test_first_call_with_unseen_ids_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, _, _ = _make_composer()
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_existing_tracking_valid_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    tracking.write(trade_ids[StrategyFamily.TREND_FOLLOWING], object())

    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_info:
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert trade_ids[StrategyFamily.TREND_FOLLOWING] in exc_info.value.colliding_trade_ids
    assert calls == []


@pytest.mark.asyncio
async def test_tracking_corrupt_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    tracking.force_status(trade_ids[StrategyFamily.BREAKOUT], "CORRUPT")

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


@pytest.mark.asyncio
async def test_tracking_unavailable_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    tracking.force_status(trade_ids[StrategyFamily.EVENT_DRIVEN], "UNAVAILABLE")

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


@pytest.mark.asyncio
async def test_provenance_valid_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, _, provenance = _make_composer()
    trade_ids = all_trade_ids()
    provenance.write(trade_ids[StrategyFamily.MEAN_REVERSION], object())

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


@pytest.mark.asyncio
async def test_provenance_corrupt_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, _, provenance = _make_composer()
    trade_ids = all_trade_ids()
    provenance.force_status(trade_ids[StrategyFamily.TREND_FOLLOWING], "CORRUPT")

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


@pytest.mark.asyncio
async def test_provenance_unavailable_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, _, provenance = _make_composer()
    trade_ids = all_trade_ids()
    provenance.force_status(trade_ids[StrategyFamily.BREAKOUT], "UNAVAILABLE")

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


@pytest.mark.asyncio
async def test_duplicate_performs_no_new_persistence_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, provenance = _make_composer()
    trade_ids = all_trade_ids()
    tracking.write(trade_ids[StrategyFamily.TREND_FOLLOWING], "seed")
    tracking.write_calls.clear()
    provenance.write_calls.clear()

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert tracking.write_calls == []
    assert provenance.write_calls == []


@pytest.mark.asyncio
async def test_all_supplied_family_ids_are_checked_not_just_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A collision on the LAST family checked must still be caught -
    proves the preflight iterates every supplied id, not just the first."""
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    last_family = list(StrategyFamily)[-1]
    tracking.write(trade_ids[last_family], object())

    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_info:
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert trade_ids[last_family] in exc_info.value.colliding_trade_ids
    assert calls == []


@pytest.mark.asyncio
async def test_no_partial_family_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only ONE of several families collides - the whole cycle (including
    every non-colliding family) must still be refused, never partially
    executed for the others."""
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    tracking.write(trade_ids[StrategyFamily.EVENT_DRIVEN], object())

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []


# --- account-position-mode independence -------------------------------------
#
# The preflight never inspects AccountPositionMode at all - it is proven
# mode-independent simply by never reaching run_runtime_cycle (where mode-
# specific issuance logic lives) once any collision is found. These three
# tests exercise the identical code path under the three names the design
# closure required explicit coverage for.


@pytest.mark.asyncio
async def test_duplicate_rejected_before_netting_specific_runtime_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    tracking.write(trade_ids[StrategyFamily.TREND_FOLLOWING], "prior NETTING-mode PENDING record")
    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert calls == []  # run_runtime_cycle (and its netting guard) never reached


@pytest.mark.asyncio
async def test_hedging_retry_cannot_overwrite_pending_or_open_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scenario the retry/idempotency closure exists to fix: HEDGING
    mode has no netting guard of its own, so only this preflight prevents
    an overwrite."""
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    prior_open_record = "prior HEDGING-mode OPEN record"
    tracking.write(trade_ids[StrategyFamily.BREAKOUT], prior_open_record)

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert calls == []
    status, stored = tracking.read(trade_ids[StrategyFamily.BREAKOUT])
    assert status == "VALID"
    assert stored == prior_open_record  # byte-identical - never overwritten


@pytest.mark.asyncio
async def test_unknown_mode_retry_cannot_overwrite_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()
    prior_record = "prior UNKNOWN-mode record"
    tracking.write(trade_ids[StrategyFamily.MEAN_REVERSION], prior_record)

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert calls == []
    _, stored = tracking.read(trade_ids[StrategyFamily.MEAN_REVERSION])
    assert stored == prior_record


# --- concurrency -------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_same_id_calls_are_serialized_runtime_executes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two ``run_cycle`` calls with identical trade_ids "simultaneously":
    the lock must fully serialize them so the second only ever sees the
    first's persisted result, never racing past preflight together."""
    call_count = 0

    def fake(**kwargs: object):
        nonlocal call_count
        call_count += 1
        from datetime import UTC, datetime

        from app.core.enums.mt5_runtime import MT5ConnectivityState
        from app.core.enums.runtime_cycle import RuntimeCycleOutcome
        from app.core.models.mt5_runtime import MT5RuntimeStatus
        from app.core.models.runtime_cycle import RuntimeCycleResult

        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome.BLOCKED,
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.TERMINAL_UNAVAILABLE),
        )

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake)

    tracking = FakeRecordPersistence()
    provenance = FakeRecordPersistence()
    composer = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=FakeFlowBootstrap(),
        mt5_client=FakeMT5Client(),
        tracking_persistence=tracking,
        provenance_persistence=provenance,
    )
    trade_ids = all_trade_ids()

    # Simulate "the first call's own run_runtime_cycle already persisted a
    # record" happening exactly once, mid-flight, by having the fake write
    # to tracking itself before returning (mirrors what the REAL
    # run_runtime_cycle does internally).
    def fake_with_write(**kwargs: object):
        result = fake(**kwargs)
        tracking.write(trade_ids[StrategyFamily.TREND_FOLLOWING], "persisted-by-first-call")
        return result

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake_with_write)

    await composer.startup()
    first = await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert call_count == 1
    assert first.outcome.value == "SERVICE_UNAVAILABLE"

    with pytest.raises(ProductionAdvisoryDuplicateCycleError):
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert call_count == 1  # runtime executed exactly once across both calls


@pytest.mark.asyncio
async def test_two_truly_concurrent_calls_lock_serializes_and_only_one_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    """Launches two ``run_cycle`` coroutines at the same time via
    ``asyncio.gather`` - the lock must ensure the second's preflight only
    ever runs after the first has fully released the lock (including any
    persistence its cycle performed), so exactly one succeeds and the
    other is rejected as a duplicate - never both succeeding."""
    call_count = 0

    def fake(**kwargs: object):
        nonlocal call_count
        call_count += 1
        from datetime import UTC, datetime

        from app.core.enums.mt5_runtime import MT5ConnectivityState
        from app.core.enums.runtime_cycle import RuntimeCycleOutcome
        from app.core.models.mt5_runtime import MT5RuntimeStatus
        from app.core.models.runtime_cycle import RuntimeCycleResult

        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome.BLOCKED,
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.TERMINAL_UNAVAILABLE),
        )

    tracking = FakeRecordPersistence()
    trade_ids = all_trade_ids()

    def fake_with_write(**kwargs: object):
        result = fake(**kwargs)
        tracking.write(trade_ids[StrategyFamily.TREND_FOLLOWING], "persisted")
        return result

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake_with_write)

    composer = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=FakeFlowBootstrap(),
        mt5_client=FakeMT5Client(),
        tracking_persistence=tracking,
        provenance_persistence=FakeRecordPersistence(),
    )

    await composer.startup()
    results = await asyncio.gather(
        composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids),
        composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, BaseException)]
    duplicates = [r for r in results if isinstance(r, ProductionAdvisoryDuplicateCycleError)]
    assert len(successes) == 1
    assert len(duplicates) == 1
    assert call_count == 1  # runtime executed exactly once


@pytest.mark.asyncio
async def test_preflight_and_runtime_call_happen_inside_the_same_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class RecordingLock:
        def __init__(self) -> None:
            import app.production_advisory.lock as lock_module

            self._inner = lock_module.ProductionAdvisoryCycleLock()

        async def __aenter__(self):
            await self._inner.__aenter__()
            events.append("lock_acquired")
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            events.append("lock_released")
            await self._inner.__aexit__(*exc_info)

    def fake(**kwargs: object):
        events.append("run_runtime_cycle_called")
        from datetime import UTC, datetime

        from app.core.enums.mt5_runtime import MT5ConnectivityState
        from app.core.enums.runtime_cycle import RuntimeCycleOutcome
        from app.core.models.mt5_runtime import MT5RuntimeStatus
        from app.core.models.runtime_cycle import RuntimeCycleResult

        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome.BLOCKED,
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.TERMINAL_UNAVAILABLE),
        )

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake)

    composer, _, _ = _make_composer()
    composer._lock = RecordingLock()  # type: ignore[assignment]

    original_preflight = composer._reject_if_duplicate_cycle

    def recording_preflight(trade_ids: object) -> None:
        events.append("preflight_checked")
        original_preflight(trade_ids)

    composer._reject_if_duplicate_cycle = recording_preflight  # type: ignore[method-assign]

    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert events == ["lock_acquired", "preflight_checked", "run_runtime_cycle_called", "lock_released"]


# --- crash window ------------------------------------------------------------


@pytest.mark.asyncio
async def test_crash_after_persistence_retry_is_refused_never_reconstructed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulates a crash: tracking was already written by a prior attempt,
    but no ``ProductionAdvisoryCycleResult`` was ever returned to that
    caller. A retry with the identical trade_ids must be refused, never
    given a fabricated/reconstructed result."""
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer, tracking, _ = _make_composer()
    trade_ids = all_trade_ids()

    # pre-seed as if a prior attempt crashed after this single write
    tracking.write(trade_ids[StrategyFamily.EVENT_DRIVEN], "crash-survivor record")

    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_info:
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)

    assert calls == []
    assert trade_ids[StrategyFamily.EVENT_DRIVEN] in exc_info.value.colliding_trade_ids


# --- duplicate-error deterministic data --------------------------------------


def test_colliding_trade_ids_are_sorted_regardless_of_discovery_order() -> None:
    from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError

    a = ProductionAdvisoryDuplicateCycleError(("z-id", "a-id", "m-id"))
    b = ProductionAdvisoryDuplicateCycleError(("a-id", "m-id", "z-id"))
    assert a.colliding_trade_ids == b.colliding_trade_ids == ("a-id", "m-id", "z-id")


def test_colliding_trade_ids_deduplicated() -> None:
    from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError

    error = ProductionAdvisoryDuplicateCycleError(("dup-id", "dup-id", "other-id"))
    assert error.colliding_trade_ids == ("dup-id", "other-id")


@pytest.mark.asyncio
async def test_same_collision_produces_same_error_data_independent_of_mapping_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.enums.strategy_router import StrategyFamily

    _fake_run_runtime_cycle(monkeypatch)
    families = list(StrategyFamily)

    composer_a, tracking_a, _ = _make_composer()
    ids_a = {family: f"TID-{family.value}" for family in families}
    tracking_a.write(ids_a[families[0]], object())
    await composer_a.startup()
    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_a:
        await composer_a.run_cycle(as_of=AS_OF, trade_ids=ids_a)

    composer_b, tracking_b, _ = _make_composer()
    ids_b = {family: f"TID-{family.value}" for family in reversed(families)}  # same values, different insertion order
    tracking_b.write(ids_b[families[0]], object())
    await composer_b.startup()
    with pytest.raises(ProductionAdvisoryDuplicateCycleError) as exc_b:
        await composer_b.run_cycle(as_of=AS_OF, trade_ids=ids_b)

    assert exc_a.value.colliding_trade_ids == exc_b.value.colliding_trade_ids


def test_duplicate_error_message_never_contains_credential_looking_content() -> None:
    """The exception message is built only from trade_id strings - no
    MT5Credentials/OpenAI api_key/any SecretStr ever reaches it."""
    from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError

    error = ProductionAdvisoryDuplicateCycleError(("TID-TREND_FOLLOWING", "TID-BREAKOUT"))
    message = str(error)
    assert "password" not in message.lower()
    assert "api_key" not in message.lower()
    assert "secret" not in message.lower()
