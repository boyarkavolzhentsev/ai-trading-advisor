"""Shared builders for High-Impact Event Risk Gate tests.

Builds real ``StrategySetupResult`` fixtures via the real Stage 5A-6C-Setup
Construction chain (reusing ``tests/setup_construction_support.py`` and its
own upstream support modules) with an explicit, caller-chosen ``as_of`` -
Setup Construction always sets ``signal_time=as_of``/
``valid_until=as_of+SIGNAL_EXECUTION_WINDOW`` (5 minutes), so every test
below controls timing purely through ``as_of`` relative to a fixed
``event_time``. Not a test module itself (no ``test_`` prefix): pytest will
not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventImportance
from app.core.enums.market import Timeframe
from app.core.enums.technical import SwingKind
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.high_impact_event import HighImpactEventContext, HighImpactEventRecord
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.setup_construction import StrategySetupResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.decision.gate import PolicyGate
from app.decision.setup_construction import SetupConstruction
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.market_evaluation_support import make_context
from tests.setup_construction_support import symbol_facts as _symbol_facts, swing, usable_market_structure
from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

EVENT_TIME = datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)
"""Fixed reference event_time used across every High-Impact Event test."""

USD_SYMBOL = "EURUSD"
WTI_SYMBOL = "XTIUSD"
UNRELATED_SYMBOL = "XAGEUR"


def record(
    *,
    event_code: str = "US_NFP",
    importance: HighImpactEventImportance = HighImpactEventImportance.HIGH,
    event_time: datetime = EVENT_TIME,
    provider_event_id: str = "1:2026-01-02",
    scope: tuple[str, ...] = ("USD",),
    name: str = "Non-Farm Payrolls",
) -> HighImpactEventRecord:
    return HighImpactEventRecord(
        provider_event_id=provider_event_id,
        event_time=event_time,
        importance=importance,
        scope=scope,
        event_code=event_code,
        name=name,
    )


def fresh_context(*, events: tuple[HighImpactEventRecord, ...], as_of: datetime, producer: str = "test_bridge") -> HighImpactEventContext:
    return HighImpactEventContext(events=events, data_quality=HighImpactEventDataQuality.FRESH, producer=producer, generated_at=as_of)


def degraded_context(
    *, data_quality: HighImpactEventDataQuality, generated_at: datetime | None = None, producer: str = "test_bridge"
) -> HighImpactEventContext:
    return HighImpactEventContext(events=(), data_quality=data_quality, producer=producer, generated_at=generated_at)


def usd_context(**overrides: object) -> MarketEvaluationContext:
    fields: dict[str, object] = {"symbol": USD_SYMBOL, "currency_exposures": ("EUR", "USD")}
    fields.update(overrides)
    return make_context(**fields)


def btc_context(**overrides: object) -> MarketEvaluationContext:
    fields: dict[str, object] = {"symbol": "BTCUSDT", "base_asset": "BTC", "network": "bitcoin"}
    fields.update(overrides)
    return make_context(**fields)


def wti_context(**overrides: object) -> MarketEvaluationContext:
    fields: dict[str, object] = {"symbol": WTI_SYMBOL}
    fields.update(overrides)
    return make_context(**fields)


def unrelated_context(**overrides: object) -> MarketEvaluationContext:
    fields: dict[str, object] = {"symbol": UNRELATED_SYMBOL, "currency_exposures": ("EUR",)}
    fields.update(overrides)
    return make_context(**fields)


def _technical_with_trend_observations_for(*, symbol: str, contract_type: object) -> TechnicalSupervisorResult:
    """Mirrors ``tests.strategy_judge_support.technical_with_trend_observations``
    exactly, with an explicit ``symbol``/``contract_type`` - that shared
    helper hardcodes the default ``BTCUSDT`` symbol, so it cannot be reused
    for a ``context`` scoped to a different instrument (e.g. the WTI/energy
    relevance tests below)."""
    results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            timeframe,
            symbol=symbol,
            contract_type=contract_type,
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),
                make_observation(dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION, value="UPWARD"),
            ),
        )
        for timeframe in DEFAULT_TIMEFRAMES[:2]
    ]
    return TechnicalSupervisor().aggregate(tuple(results))


def constructed_setup_result(*, context: MarketEvaluationContext, as_of: datetime) -> StrategySetupResult:
    """A real, Setup-``CONSTRUCTED`` ``TREND_FOLLOWING`` result at ``as_of``
    (so ``signal_time == as_of``, ``valid_until == as_of + 5min``), scoped
    to ``context``'s own symbol/currency/asset identity - built directly
    from ``route_and_judge``/``PolicyGate`` (rather than
    ``tests.setup_construction_support.trend_following_policy_result``,
    which hardcodes the default ``BTCUSDT`` context) so the real,
    embedded ``MarketEvaluationContext`` the gate reads is ``context``
    itself, not a default."""
    technical = _technical_with_trend_observations_for(symbol=context.symbol, contract_type=context.contract_type)
    _router_result, judge_result = route_and_judge(technical=technical, context=context)
    policy = PolicyGate().apply(strategy_judge_result=judge_result)
    ms = usable_market_structure(
        swings=(swing(kind=SwingKind.LOW, price=Decimal("95"), candle_time=as_of - timedelta(hours=1)),), symbol=context.symbol
    )
    facts = _symbol_facts(symbol=context.symbol, ask=Decimal("110"), bid=Decimal("109.5"))
    return SetupConstruction().construct(
        strategy_policy_result=policy,
        as_of=as_of,
        symbol_facts=facts,
        m15_market_structure=ms,
        broker_symbol=context.symbol,
        binance_reference_price=Decimal("110"),
        max_price_basis_divergence_percent=Decimal("100"),
    )


def constructed_setup_result_with_event_driven_blocked(*, context: MarketEvaluationContext, as_of: datetime) -> StrategySetupResult:
    """Same as ``constructed_setup_result``, but also makes ``EVENT_DRIVEN``
    Policy-``ELIGIBLE_FOR_RISK_REVIEW`` (via a real News/Sentiment thesis) -
    Setup Construction then unconditionally blocks it with
    ``FAMILY_SETUP_UNAVAILABLE`` (per its own approved V1 design, mirroring
    ``tests.test_decision_risk_pipeline.test_setup_bridge_preserves_exact_risk_per_unit_and_zero_sentinel_for_blocked``),
    giving a genuine simultaneously-``CONSTRUCTED``/Setup-``BLOCKED`` fixture."""
    technical = _technical_with_trend_observations_for(symbol=context.symbol, contract_type=context.contract_type)
    external = external_with_news_sentiment(symbol=context.symbol, provider_signs={"provider_a": "POSITIVE", "provider_b": "POSITIVE"})
    _router_result, judge_result = route_and_judge(technical=technical, external=external, context=context)
    policy = PolicyGate().apply(strategy_judge_result=judge_result)
    ms = usable_market_structure(
        swings=(swing(kind=SwingKind.LOW, price=Decimal("95"), candle_time=as_of - timedelta(hours=1)),), symbol=context.symbol
    )
    facts = _symbol_facts(symbol=context.symbol, ask=Decimal("110"), bid=Decimal("109.5"))
    return SetupConstruction().construct(
        strategy_policy_result=policy,
        as_of=as_of,
        symbol_facts=facts,
        m15_market_structure=ms,
        broker_symbol=context.symbol,
        binance_reference_price=Decimal("110"),
        max_price_basis_divergence_percent=Decimal("100"),
    )


__all__ = [
    "EVENT_TIME",
    "USD_SYMBOL",
    "UNRELATED_SYMBOL",
    "WTI_SYMBOL",
    "btc_context",
    "constructed_setup_result",
    "constructed_setup_result_with_event_driven_blocked",
    "degraded_context",
    "fresh_context",
    "record",
    "unrelated_context",
    "usd_context",
    "wti_context",
]
