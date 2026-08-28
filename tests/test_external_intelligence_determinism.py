"""Determinism: identical inputs produce identical, order-independent results;
no wall-clock/randomness anywhere in the analyst layer.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
from app.core.models.economic_event import EconomicEvent
from app.external_intelligence_analysts import MacroAnalystConfig, MacroEventAnalyst, OnChainAnalyst, OnChainAnalystConfig
from app.core.models.network_activity_observation import NetworkActivityObservation


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


def test_macro_analyst_is_deterministic_given_identical_inputs(now: datetime) -> None:
    analyst = MacroEventAnalyst()
    config = MacroAnalystConfig(proximity_window=timedelta(hours=24), staleness_threshold=timedelta(hours=6))
    events = [_event(now, provider_event_id=f"evt-{i}") for i in range(3)]

    first = analyst.analyze(events, currency="USD", analysis_time=now, config=config)
    second = analyst.analyze(events, currency="USD", analysis_time=now, config=config)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_macro_analyst_output_is_independent_of_input_ordering(now: datetime) -> None:
    analyst = MacroEventAnalyst()
    config = MacroAnalystConfig(proximity_window=timedelta(hours=24), staleness_threshold=timedelta(hours=6))
    events = [
        _event(now + timedelta(hours=offset), provider_event_id=f"evt-{offset}") for offset in (3, 1, 4, 0, 2)
    ]

    forward = analyst.analyze(events, currency="USD", analysis_time=now, config=config)
    backward = analyst.analyze(list(reversed(events)), currency="USD", analysis_time=now, config=config)

    forward_subjects = sorted(o.subject for o in forward.observations if o.subject)
    backward_subjects = sorted(o.subject for o in backward.observations if o.subject)
    assert forward_subjects == backward_subjects


def test_on_chain_analyst_output_is_independent_of_input_ordering(now: datetime) -> None:
    analyst = OnChainAnalyst()
    config = OnChainAnalystConfig(staleness_threshold=timedelta(days=3))
    observations = [
        NetworkActivityObservation(
            provider="glassnode",
            provider_series_id="btc-activity",
            asset="BTC",
            network="bitcoin",
            observation_time=now - timedelta(days=offset),
            received_at=now,
            active_addresses=900_000 + offset * 1000,
        )
        for offset in (3, 1, 4, 0, 2)
    ]

    forward = analyst.analyze(observations, [], [], [], asset="BTC", network="bitcoin", analysis_time=now, config=config)
    backward = analyst.analyze(
        list(reversed(observations)), [], [], [], asset="BTC", network="bitcoin", analysis_time=now, config=config
    )
    assert forward.model_dump() == backward.model_dump()


def test_no_wall_clock_randomness_or_network_calls_in_any_analyst() -> None:
    from app.external_intelligence_analysts import macro_event, news_sentiment, on_chain, rates_yield
    from app.external_intelligence_analysts import base as base_module

    forbidden = ("datetime.now", "utcnow", "time.time", "random.", "uuid.", "requests.", "httpx.", "socket.")
    for module in (base_module, macro_event, rates_yield, news_sentiment, on_chain):
        source = inspect.getsource(module)
        for term in forbidden:
            assert term not in source, f"{module.__name__} contains forbidden term {term!r}"
