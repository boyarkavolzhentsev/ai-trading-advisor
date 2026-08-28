"""Stage 4F evidence traceability: exact source identity, semantic
timestamps, retained received_at, two-input calculations citing two records.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
from app.core.enums.external_intelligence_analysis import ExternalIntelligenceDimension
from app.core.models.economic_event import EconomicEvent
from app.external_intelligence_analysts import MacroAnalystConfig, MacroEventAnalyst

CONFIG = MacroAnalystConfig(proximity_window=timedelta(hours=24), staleness_threshold=timedelta(hours=6))


def _event(now: datetime, **overrides: object) -> EconomicEvent:
    fields: dict[str, object] = {
        "provider": "tradingeconomics",
        "provider_event_id": "cpi-2026-01",
        "country": "US",
        "currency": "USD",
        "category": EconomicCategory.CPI,
        "name": "CPI YoY",
        "event_time": now,
        "received_at": now,
        "status": EconomicEventStatus.SCHEDULED,
    }
    fields.update(overrides)
    return EconomicEvent(**fields)


def test_evidence_cites_exact_source_provider_and_record_id(now: datetime) -> None:
    event = _event(now, provider="tradingeconomics", provider_event_id="cpi-2026-01")
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    for evidence in result.evidence:
        assert evidence.source_provider == "tradingeconomics"
        assert evidence.source_record_id == "cpi-2026-01"


def test_evidence_source_timestamp_is_semantic_not_received_at(now: datetime) -> None:
    event_time = now - timedelta(hours=2)
    received_at = now - timedelta(days=50)
    event = _event(now, event_time=event_time, received_at=received_at)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    for evidence in result.evidence:
        assert evidence.source_timestamp == event_time
        assert evidence.source_timestamp != received_at


def test_evidence_retains_received_at_for_audit(now: datetime) -> None:
    received_at = now - timedelta(hours=3)
    event = _event(now, received_at=received_at)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    for evidence in result.evidence:
        assert evidence.source_received_at == received_at


def test_two_input_calculation_cites_two_evidence_records(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    surprise_observations = [o for o in result.observations if o.dimension is ExternalIntelligenceDimension.SURPRISE]
    assert len(surprise_observations) == 1
    # SURPRISE cites one evidence entry recording (actual, reference=forecast) -
    # a single-fact-per-entry citation, never a bundled two-value entry.
    assert len(surprise_observations[0].evidence_refs) == 1
    cited = result.evidence[surprise_observations[0].evidence_refs[0]]
    assert cited.observed_value == "3.2"
    assert cited.reference_value == "3.0"


def test_revision_direction_cites_two_separate_evidence_records(now: datetime) -> None:
    prior = _event(
        now, provider_event_id="nfp-2026-01", status=EconomicEventStatus.RELEASED, actual=Decimal("150"), revision_number=0
    )
    latest = _event(
        now, provider_event_id="nfp-2026-01", status=EconomicEventStatus.REVISED, actual=Decimal("180"), revision_number=1
    )
    analyst = MacroEventAnalyst()
    result = analyst.analyze([prior, latest], currency="USD", analysis_time=now, config=CONFIG)
    revision_observations = [
        o for o in result.observations if o.dimension is ExternalIntelligenceDimension.REVISION_DIRECTION
    ]
    assert len(revision_observations) == 1
    refs = revision_observations[0].evidence_refs
    assert len(refs) == 2
    cited_values = {result.evidence[r].observed_value for r in refs}
    assert cited_values == {"150", "180"}


def test_evidence_refs_are_exact_and_within_bounds(now: datetime) -> None:
    events = [_event(now, provider_event_id=f"evt-{i}") for i in range(3)]
    analyst = MacroEventAnalyst()
    result = analyst.analyze(events, currency="USD", analysis_time=now, config=CONFIG)
    for observation in result.observations:
        for ref in observation.evidence_refs:
            assert 0 <= ref < len(result.evidence)


def test_evidence_never_copies_the_entire_source_record(now: datetime) -> None:
    """Evidence carries a fixed, small schema - never the full source
    record's own fields (e.g. ``category``/``revision_number`` from
    ``EconomicEvent``)."""
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    for evidence in result.evidence:
        assert not hasattr(evidence, "category")
        assert not hasattr(evidence, "revision_number")
        assert not hasattr(evidence, "status")
