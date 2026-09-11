"""Cycle-level request idempotency tests (corrective design closure,
"CYCLE-LEVEL IDEMPOTENCY"): ``logical_cycle_id`` denotes ONE logical advisory
attempt, regardless of first-attempt outcome.

Status-outcome/exception/concurrency tests use a narrow ``FakeComposer`` (no
real MT5/Binance/OpenAI). Restart/corruption/concurrency-at-the-filesystem
tests use the REAL, file-backed ``CycleReceiptPersistence`` under ``tmp_path``
- never ``./data/cycle_receipts`` - so no repository persistence is ever
touched by this test module.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

import app.application.cycle_receipt as cycle_receipt_module
from app.application.advisory_service import ApplicationAdvisoryService
from app.application.cycle_receipt import CycleReceiptClaimResult, CycleReceiptPersistence
from app.application.errors import DuplicateCycleError, InternalApplicationError
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.application_support import (
    FakeCycleReceiptPersistence,
    one_family_actionable_others_ineligible,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)


class FakeComposer:
    """Records every ``run_cycle`` call. Returns a caller-configured
    ``ProductionAdvisoryCycleResult`` or raises a caller-configured
    exception - never touches MT5/Binance/OpenAI/a real
    ``ProductionAdvisoryComposer``. Mirrors ``tests/test_application_service.
    py``'s own identical fake (kept as an independent, narrow copy rather
    than a cross-test-module import)."""

    def __init__(self, *, result=None, run_cycle_exception: Exception | None = None) -> None:
        self._result = result
        self._run_cycle_exception = run_cycle_exception
        self.startup_calls = 0
        self.shutdown_calls = 0
        self.run_cycle_calls: list[dict[str, object]] = []

    async def startup(self) -> None:
        self.startup_calls += 1

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def run_cycle(self, *, as_of, trade_ids):
        await asyncio.sleep(0)  # yields to the event loop, as a real await-bearing call would
        self.run_cycle_calls.append({"as_of": as_of, "trade_ids": trade_ids})
        if self._run_cycle_exception is not None:
            raise self._run_cycle_exception
        assert self._result is not None
        return self._result


def _no_trade_cycle():
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.READY)
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)


def _service_unavailable_cycle():
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.BLOCKED)
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE)


def _degraded_no_recommendation_cycle():
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED)
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)


def _cycle_with_one_recommendation(*, degraded: bool):
    family = StrategyFamily.TREND_FOLLOWING
    trade_id = "TID__TREND_FOLLOWING"
    drp, frcr = one_family_actionable_others_ineligible(family, trade_id)
    tracking = (tracking_outcome(trade_id, MT5TrackedRecommendationCreationOutcome.CREATED),)
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED if degraded else RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        new_tracking_persistence_outcomes=tracking,
    )
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)


# --- B: status-by-status replay matrix -----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("build_cycle",),
    [
        (_no_trade_cycle,),
        (_service_unavailable_cycle,),
        (_degraded_no_recommendation_cycle,),
        (lambda: _cycle_with_one_recommendation(degraded=False),),  # READY + recommendation
        (lambda: _cycle_with_one_recommendation(degraded=True),),  # DEGRADED + recommendation
    ],
    ids=["NO_TRADE", "SERVICE_UNAVAILABLE", "DEGRADED_no_recommendation", "READY_with_recommendation", "DEGRADED_with_recommendation"],
)
async def test_same_id_twice_rejects_regardless_of_first_outcome(build_cycle) -> None:
    composer = FakeComposer(result=build_cycle())
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=FakeCycleReceiptPersistence())

    first = await service.create_advisory(logical_cycle_id="cycle-1")
    assert first is not None

    with pytest.raises(DuplicateCycleError) as exc_info:
        await service.create_advisory(logical_cycle_id="cycle-1")

    assert exc_info.value.logical_cycle_id == "cycle-1"
    assert exc_info.value.colliding_trade_ids == ()
    assert len(composer.run_cycle_calls) == 1  # the composer was never called a second time


@pytest.mark.asyncio
async def test_different_id_allowed() -> None:
    composer = FakeComposer(result=_no_trade_cycle())
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=FakeCycleReceiptPersistence())

    await service.create_advisory(logical_cycle_id="cycle-1")
    await service.create_advisory(logical_cycle_id="cycle-2")

    assert len(composer.run_cycle_calls) == 2


# --- G: crash-after-claim (exception) semantics --------------------------


@pytest.mark.asyncio
async def test_composer_exception_after_claim_still_consumes_the_id() -> None:
    composer = FakeComposer(run_cycle_exception=RuntimeError("simulated crash mid-cycle"))
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=FakeCycleReceiptPersistence())

    with pytest.raises(InternalApplicationError):
        await service.create_advisory(logical_cycle_id="cycle-1")
    assert len(composer.run_cycle_calls) == 1

    with pytest.raises(DuplicateCycleError):
        await service.create_advisory(logical_cycle_id="cycle-1")
    assert len(composer.run_cycle_calls) == 1  # composer is NOT called again


# --- H: restart, real file-backed persistence -----------------------------


@pytest.mark.asyncio
async def test_restart_same_receipt_directory_rejects_completed_id(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "cycle_receipts"

    composer_1 = FakeComposer(result=_no_trade_cycle())
    service_1 = ApplicationAdvisoryService(composer=composer_1, cycle_receipt_persistence=CycleReceiptPersistence(receipt_dir))
    await service_1.create_advisory(logical_cycle_id="e2e_offline_001")

    # fresh service instance, fresh CycleReceiptPersistence object, SAME directory
    composer_2 = FakeComposer(result=_no_trade_cycle())
    service_2 = ApplicationAdvisoryService(composer=composer_2, cycle_receipt_persistence=CycleReceiptPersistence(receipt_dir))

    with pytest.raises(DuplicateCycleError):
        await service_2.create_advisory(logical_cycle_id="e2e_offline_001")
    assert composer_2.run_cycle_calls == []

    await service_2.create_advisory(logical_cycle_id="e2e_offline_002")
    assert len(composer_2.run_cycle_calls) == 1


# --- I: concurrency --------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_same_id_exactly_one_reaches_composer(tmp_path: Path) -> None:
    composer = FakeComposer(result=_no_trade_cycle())
    service = ApplicationAdvisoryService(
        composer=composer, cycle_receipt_persistence=CycleReceiptPersistence(tmp_path / "cycle_receipts")
    )

    results = await asyncio.gather(
        service.create_advisory(logical_cycle_id="concurrent-1"),
        service.create_advisory(logical_cycle_id="concurrent-1"),
        return_exceptions=True,
    )

    duplicate_count = sum(1 for r in results if isinstance(r, DuplicateCycleError))
    success_count = sum(1 for r in results if not isinstance(r, BaseException))
    assert duplicate_count == 1
    assert success_count == 1
    assert len(composer.run_cycle_calls) == 1


def test_two_independent_persistence_instances_same_directory_agree(tmp_path: Path) -> None:
    """Cross-instance (i.e. cross-process, in spirit) safety: two separate
    ``CycleReceiptPersistence`` Python objects, sharing no in-memory state,
    pointed at the same directory - the second sees the first's claim purely
    through the filesystem, exactly as two separate OS processes would."""
    from datetime import UTC, datetime

    directory = tmp_path / "cycle_receipts"
    persistence_a = CycleReceiptPersistence(directory)
    persistence_b = CycleReceiptPersistence(directory)

    now = datetime.now(UTC)
    assert persistence_a.claim("shared-id", accepted_at=now) is CycleReceiptClaimResult.CREATED
    assert persistence_b.claim("shared-id", accepted_at=now) is CycleReceiptClaimResult.ALREADY_EXISTS


# --- J: corrupt/partial receipt --------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_content", [b"", b"{not valid json", b"\x00\x01\x02"], ids=["empty", "malformed_json", "binary_garbage"])
async def test_corrupt_or_partial_receipt_fails_closed(tmp_path: Path, existing_content: bytes) -> None:
    receipt_dir = tmp_path / "cycle_receipts"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "cycle-1.json").write_bytes(existing_content)

    composer = FakeComposer(result=_no_trade_cycle())
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=CycleReceiptPersistence(receipt_dir))

    with pytest.raises(DuplicateCycleError):
        await service.create_advisory(logical_cycle_id="cycle-1")
    assert composer.run_cycle_calls == []


def test_claim_on_corrupt_file_returns_already_exists_directly(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    receipt_dir = tmp_path / "cycle_receipts"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "corrupt-id.json").write_bytes(b"not json at all")

    persistence = CycleReceiptPersistence(receipt_dir)
    result = persistence.claim("corrupt-id", accepted_at=datetime.now(UTC))
    assert result is CycleReceiptClaimResult.ALREADY_EXISTS


# --- basic claim-primitive behavior ----------------------------------------


def test_claim_creates_receipt_file_with_expected_shape(tmp_path: Path) -> None:
    import json
    from datetime import UTC, datetime

    directory = tmp_path / "cycle_receipts"
    persistence = CycleReceiptPersistence(directory)
    accepted_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    result = persistence.claim("my_cycle_1", accepted_at=accepted_at)
    assert result is CycleReceiptClaimResult.CREATED

    receipt_path = directory / "my_cycle_1.json"
    assert receipt_path.is_file()
    body = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert body == {
        "schema_version": 1,
        "logical_cycle_id": "my_cycle_1",
        "accepted_at": accepted_at.isoformat(),
    }


def test_second_claim_same_id_returns_already_exists_and_never_overwrites(tmp_path: Path) -> None:
    import json
    from datetime import UTC, datetime

    directory = tmp_path / "cycle_receipts"
    persistence = CycleReceiptPersistence(directory)
    first_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    second_time = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)

    assert persistence.claim("my_cycle_1", accepted_at=first_time) is CycleReceiptClaimResult.CREATED
    assert persistence.claim("my_cycle_1", accepted_at=second_time) is CycleReceiptClaimResult.ALREADY_EXISTS

    body = json.loads((directory / "my_cycle_1.json").read_text(encoding="utf-8"))
    assert body["accepted_at"] == first_time.isoformat()  # never rewritten by the second, losing claim


# --- pre-commit durability review: post-create metadata-write failures ----
#
# Once os.open(..., O_CREAT | O_EXCL) itself succeeds, logical_cycle_id is
# already permanently consumed - existence alone is the authoritative fact
# (see CycleReceiptPersistence.claim's own docstring). Every test below
# injects a failure strictly AFTER that point (fdopen/write/flush/fsync) and
# proves: first claim() still returns CREATED, the receipt file exists, a
# second claim() returns ALREADY_EXISTS, and the file is never deleted or
# rewritten by either claim.


class _ControlledHandle:
    """A minimal stand-in for the real file object ``os.fdopen`` would
    return - wraps the SAME real fd (opened for real by the real, unmocked
    ``os.open`` call), so the on-disk file itself is entirely real. Only
    ``write``/``flush`` are made to fail on demand; ``fileno``/``close`` stay
    real so ``os.fsync(handle.fileno())`` and the ``with handle:`` context
    manager's cleanup both still behave exactly as they would in production.
    """

    def __init__(self, fd: int, *, fail_on: str | None) -> None:
        self._fd = fd
        self._fail_on = fail_on

    def write(self, data: bytes) -> int:
        if self._fail_on == "write":
            raise OSError("simulated write failure")
        return os.write(self._fd, data)

    def flush(self) -> None:
        if self._fail_on == "flush":
            raise OSError("simulated flush failure")

    def fileno(self) -> int:
        return self._fd

    def close(self) -> None:
        os.close(self._fd)

    def __enter__(self) -> "_ControlledHandle":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.close()
        return False


def _assert_created_then_second_claim_rejects_without_rewrite(directory: Path, logical_cycle_id: str) -> None:
    persistence = CycleReceiptPersistence(directory)
    path = directory / f"{logical_cycle_id}.json"
    assert path.is_file()
    content_after_first = path.read_bytes()

    second = persistence.claim(logical_cycle_id, accepted_at=datetime.now(UTC))
    assert second is CycleReceiptClaimResult.ALREADY_EXISTS
    assert path.is_file()
    assert path.read_bytes() == content_after_first  # never rewritten, never deleted


def test_claim_created_when_fdopen_fails_after_exclusive_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "cycle_receipts"

    def failing_fdopen(fd: int, mode: str):
        raise OSError("simulated fdopen failure")

    monkeypatch.setattr(cycle_receipt_module.os, "fdopen", failing_fdopen)

    persistence = CycleReceiptPersistence(directory)
    result = persistence.claim("cycle-fdopen-fail", accepted_at=datetime.now(UTC))
    assert result is CycleReceiptClaimResult.CREATED
    monkeypatch.undo()  # restore real os.fdopen before the second claim/read below

    _assert_created_then_second_claim_rejects_without_rewrite(directory, "cycle-fdopen-fail")


def test_claim_created_when_write_fails_after_exclusive_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "cycle_receipts"

    def controlled_fdopen(fd: int, mode: str) -> _ControlledHandle:
        return _ControlledHandle(fd, fail_on="write")

    monkeypatch.setattr(cycle_receipt_module.os, "fdopen", controlled_fdopen)

    persistence = CycleReceiptPersistence(directory)
    result = persistence.claim("cycle-write-fail", accepted_at=datetime.now(UTC))
    assert result is CycleReceiptClaimResult.CREATED
    monkeypatch.undo()

    _assert_created_then_second_claim_rejects_without_rewrite(directory, "cycle-write-fail")


def test_claim_created_when_flush_fails_after_exclusive_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "cycle_receipts"

    def controlled_fdopen(fd: int, mode: str) -> _ControlledHandle:
        return _ControlledHandle(fd, fail_on="flush")

    monkeypatch.setattr(cycle_receipt_module.os, "fdopen", controlled_fdopen)

    persistence = CycleReceiptPersistence(directory)
    result = persistence.claim("cycle-flush-fail", accepted_at=datetime.now(UTC))
    assert result is CycleReceiptClaimResult.CREATED
    monkeypatch.undo()

    _assert_created_then_second_claim_rejects_without_rewrite(directory, "cycle-flush-fail")


def test_claim_created_when_fsync_fails_after_exclusive_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "cycle_receipts"

    def failing_fsync(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(cycle_receipt_module.os, "fsync", failing_fsync)

    persistence = CycleReceiptPersistence(directory)
    result = persistence.claim("cycle-fsync-fail", accepted_at=datetime.now(UTC))
    assert result is CycleReceiptClaimResult.CREATED
    monkeypatch.undo()

    _assert_created_then_second_claim_rejects_without_rewrite(directory, "cycle-fsync-fail")


# --- pre-commit durability review: pre-create failures must NOT consume ---


def test_claim_raises_and_does_not_consume_on_pre_create_open_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure from os.open() OTHER than FileExistsError (e.g. a
    permissions error) happens strictly BEFORE exclusive creation succeeds -
    it must propagate (never be swallowed into CREATED), and the
    logical_cycle_id must remain genuinely unclaimed: a later, unpatched
    claim() for the same id must still succeed normally."""
    directory = tmp_path / "cycle_receipts"

    def failing_open(path: object, flags: int) -> int:
        raise PermissionError("simulated permission denied")

    monkeypatch.setattr(cycle_receipt_module.os, "open", failing_open)
    persistence = CycleReceiptPersistence(directory)

    with pytest.raises(PermissionError):
        persistence.claim("cycle-preopen-fail", accepted_at=datetime.now(UTC))

    assert not (directory / "cycle-preopen-fail.json").exists()
    monkeypatch.undo()

    # the id was never actually consumed - a normal, unpatched claim succeeds
    assert persistence.claim("cycle-preopen-fail", accepted_at=datetime.now(UTC)) is CycleReceiptClaimResult.CREATED


def test_claim_raises_and_does_not_consume_on_mkdir_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "cycle_receipts"

    def failing_mkdir(self: Path, *a: object, **kw: object) -> None:
        raise PermissionError("simulated mkdir permission denied")

    monkeypatch.setattr(cycle_receipt_module.Path, "mkdir", failing_mkdir)
    persistence = CycleReceiptPersistence(directory)

    with pytest.raises(PermissionError):
        persistence.claim("cycle-mkdir-fail", accepted_at=datetime.now(UTC))

    monkeypatch.undo()
    assert not directory.exists() or not (directory / "cycle-mkdir-fail.json").exists()
    assert persistence.claim("cycle-mkdir-fail", accepted_at=datetime.now(UTC)) is CycleReceiptClaimResult.CREATED


# --- pre-commit durability review: Application-level proof ----------------


@pytest.mark.asyncio
async def test_metadata_write_failure_still_enforces_single_cycle_at_application_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real Application seam, not just the persistence unit: exclusive
    create succeeds but the receipt body write fails - the first
    create_advisory call must still run the composer exactly once and
    return normally (the write failure is not surfaced as an error at this
    layer at all - see CycleReceiptPersistence.claim's own docstring), and a
    second call with the SAME logical_cycle_id must be rejected with
    DuplicateCycleError, with the composer call count remaining exactly
    one."""
    directory = tmp_path / "cycle_receipts"
    persistence = CycleReceiptPersistence(directory)
    composer = FakeComposer(result=_no_trade_cycle())
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=persistence)

    def controlled_fdopen(fd: int, mode: str) -> _ControlledHandle:
        return _ControlledHandle(fd, fail_on="write")

    monkeypatch.setattr(cycle_receipt_module.os, "fdopen", controlled_fdopen)
    first = await service.create_advisory(logical_cycle_id="cycle-app-write-fail")
    assert first is not None
    assert len(composer.run_cycle_calls) == 1
    monkeypatch.undo()

    with pytest.raises(DuplicateCycleError):
        await service.create_advisory(logical_cycle_id="cycle-app-write-fail")
    assert len(composer.run_cycle_calls) == 1  # composer never called a second time


@pytest.mark.asyncio
async def test_pre_create_claim_failure_maps_to_internal_application_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-create claim failure (never a caller-input problem, never a
    duplicate) must surface as a sanitized InternalApplicationError - never
    a raw OSError, and never leaking the receipt directory's filesystem
    path into the exception's own outward message."""
    directory = tmp_path / "cycle_receipts"
    persistence = CycleReceiptPersistence(directory)
    composer = FakeComposer(result=_no_trade_cycle())
    service = ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=persistence)

    def failing_open(path: object, flags: int) -> int:
        raise PermissionError(f"simulated permission denied: {path}")

    monkeypatch.setattr(cycle_receipt_module.os, "open", failing_open)

    with pytest.raises(InternalApplicationError) as exc_info:
        await service.create_advisory(logical_cycle_id="cycle-app-preopen-fail")

    assert str(directory) not in str(exc_info.value)
    assert composer.run_cycle_calls == []
