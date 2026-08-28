"""Stage 4F ``MacroEventAnalyst`` deterministic calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventImportance, EconomicEventStatus
from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RevisionDirection,
    SurpriseDirection,
)
from app.core.enums.quality import FeatureQuality
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


def _dims(result, dimension: ExternalIntelligenceDimension):
    return [o for o in result.observations if o.dimension is dimension]


def test_abstains_with_no_events(now: datetime) -> None:
    analyst = MacroEventAnalyst()
    result = analyst.analyze([], currency="USD", analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert result.abstention_reasons


def test_surprise_above_forecast(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    surprises = _dims(result, ExternalIntelligenceDimension.SURPRISE)
    assert len(surprises) == 1
    assert surprises[0].value == SurpriseDirection.ABOVE_FORECAST.value


def test_surprise_below_forecast(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("2.5"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    surprises = _dims(result, ExternalIntelligenceDimension.SURPRISE)
    assert surprises[0].value == SurpriseDirection.BELOW_FORECAST.value


def test_surprise_at_forecast_exact_zero(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.0"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    surprises = _dims(result, ExternalIntelligenceDimension.SURPRISE)
    assert surprises[0].value == SurpriseDirection.AT_FORECAST.value


def test_missing_forecast_omits_surprise(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), forecast=None)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.SURPRISE) == []


def test_missing_actual_omits_surprise_and_actual_vs_previous(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.SCHEDULED, forecast=Decimal("3.0"), previous=Decimal("2.9"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.SURPRISE) == []
    assert _dims(result, ExternalIntelligenceDimension.ACTUAL_VS_PREVIOUS) == []


def test_actual_vs_previous_above(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), previous=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    dims = _dims(result, ExternalIntelligenceDimension.ACTUAL_VS_PREVIOUS)
    assert dims[0].value == "ABOVE_PREVIOUS"


def test_revision_direction_up(now: datetime) -> None:
    prior = _event(
        now, provider_event_id="nfp-2026-01", status=EconomicEventStatus.RELEASED, actual=Decimal("150"), revision_number=0
    )
    latest = _event(
        now, provider_event_id="nfp-2026-01", status=EconomicEventStatus.REVISED, actual=Decimal("180"), revision_number=1
    )
    analyst = MacroEventAnalyst()
    result = analyst.analyze([prior, latest], currency="USD", analysis_time=now, config=CONFIG)
    revisions = _dims(result, ExternalIntelligenceDimension.REVISION_DIRECTION)
    assert len(revisions) == 1
    assert revisions[0].value == RevisionDirection.REVISED_UP.value


def test_revision_direction_requires_two_valid_revisions(now: datetime) -> None:
    only_one = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("150"), revision_number=0)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([only_one], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.REVISION_DIRECTION) == []


def test_event_proximity_within_window(now: datetime) -> None:
    event = _event(now, event_time=now + timedelta(hours=2))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    proximity = _dims(result, ExternalIntelligenceDimension.EVENT_PROXIMITY)
    assert proximity[0].value == "WITHIN_WINDOW"


def test_event_proximity_outside_window(now: datetime) -> None:
    event = _event(now, event_time=now + timedelta(hours=48))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    proximity = _dims(result, ExternalIntelligenceDimension.EVENT_PROXIMITY)
    assert proximity[0].value == "OUTSIDE_WINDOW"


def test_event_proximity_already_occurred(now: datetime) -> None:
    event = _event(now, event_time=now - timedelta(minutes=1))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    proximity = _dims(result, ExternalIntelligenceDimension.EVENT_PROXIMITY)
    assert proximity[0].value == "ALREADY_OCCURRED"


def test_event_presence_no_events_is_unreachable_since_empty_list_abstains(now: datetime) -> None:
    analyst = MacroEventAnalyst()
    result = analyst.analyze([], currency="USD", analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_event_presence_single_event(now: datetime) -> None:
    event = _event(now)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    presence = _dims(result, ExternalIntelligenceDimension.EVENT_PRESENCE)
    assert presence[0].value == "SINGLE_EVENT"


def test_event_presence_multiple_events(now: datetime) -> None:
    events = [_event(now, provider_event_id=f"evt-{i}") for i in range(3)]
    analyst = MacroEventAnalyst()
    result = analyst.analyze(events, currency="USD", analysis_time=now, config=CONFIG)
    presence = _dims(result, ExternalIntelligenceDimension.EVENT_PRESENCE)
    assert presence[0].value == "MULTIPLE_EVENTS"


def test_event_importance_pass_through(now: datetime) -> None:
    event = _event(now, importance=EconomicEventImportance.HIGH)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    importance = _dims(result, ExternalIntelligenceDimension.EVENT_IMPORTANCE)
    assert importance[0].value == "HIGH"


def test_missing_importance_omits_event_importance(now: datetime) -> None:
    event = _event(now, importance=None)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.EVENT_IMPORTANCE) == []


def test_provider_disagreement_retained_as_separate_observations(now: datetime) -> None:
    """Two providers reporting conflicting surprises for a similarly-scoped
    event are retained as two independent SURPRISE observations, never
    merged/averaged."""
    event_a = _event(
        now, provider="providerA", provider_event_id="cpi-a", status=EconomicEventStatus.RELEASED,
        actual=Decimal("3.5"), forecast=Decimal("3.0"),
    )
    event_b = _event(
        now, provider="providerB", provider_event_id="cpi-b", status=EconomicEventStatus.RELEASED,
        actual=Decimal("2.5"), forecast=Decimal("3.0"),
    )
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event_a, event_b], currency="USD", analysis_time=now, config=CONFIG)
    surprises = _dims(result, ExternalIntelligenceDimension.SURPRISE)
    values = {s.value for s in surprises}
    assert values == {SurpriseDirection.ABOVE_FORECAST.value, SurpriseDirection.BELOW_FORECAST.value}


def test_stale_event_is_marked_stale_using_event_time(now: datetime) -> None:
    event = _event(now, event_time=now - timedelta(hours=10), status=EconomicEventStatus.RELEASED, actual=Decimal("1"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    proximity = _dims(result, ExternalIntelligenceDimension.EVENT_PROXIMITY)
    assert proximity[0].quality is FeatureQuality.STALE


def test_received_at_does_not_affect_staleness(now: datetime) -> None:
    """A recent event_time with a very old received_at must still be VALID -
    staleness is never driven by received_at."""
    event = _event(
        now,
        event_time=now,
        received_at=now - timedelta(days=365),
        status=EconomicEventStatus.RELEASED,
        actual=Decimal("1"),
    )
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    proximity = _dims(result, ExternalIntelligenceDimension.EVENT_PROXIMITY)
    assert proximity[0].quality is FeatureQuality.VALID


def test_no_partial_quality_ever_emitted(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("3.2"), forecast=Decimal("3.0"))
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="USD", analysis_time=now, config=CONFIG)
    for observation in result.observations:
        assert observation.quality is not FeatureQuality.PARTIAL
    assert result.quality is not FeatureQuality.PARTIAL


def test_result_scope_is_currency_only(now: datetime) -> None:
    event = _event(now)
    analyst = MacroEventAnalyst()
    result = analyst.analyze([event], currency="EUR", analysis_time=now, config=CONFIG)
    assert result.currency == "EUR"
    assert result.symbol is None
    assert result.asset is None
    assert result.network is None
