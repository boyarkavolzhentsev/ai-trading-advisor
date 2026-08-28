"""Stage 4F ``RatesYieldAnalyst`` deterministic calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.external_intelligence_analysis import (
    CurveSlopeState,
    CurveSlopeTrend,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RateTrend,
    RealNominalRelationship,
)
from app.core.enums.quality import FeatureQuality
from app.core.enums.rates import GovernmentYieldType, PolicyRateKind, SeriesUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor
from app.external_intelligence_analysts import RatesYieldAnalyst, RatesYieldAnalystConfig

CONFIG = RatesYieldAnalystConfig(staleness_threshold=timedelta(days=10))


def _policy(now: datetime, **overrides: object) -> PolicyRateObservation:
    fields: dict[str, object] = {
        "provider": "fred",
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


def _yield_obs(now: datetime, **overrides: object) -> GovernmentYieldObservation:
    fields: dict[str, object] = {
        "provider": "fred",
        "provider_series_id": "us-10y-nom",
        "country": "US",
        "currency": "USD",
        "yield_type": GovernmentYieldType.NOMINAL,
        "tenor": Tenor.of_years(10),
        "value": Decimal("4.0"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return GovernmentYieldObservation(**fields)


def _dims(result, dimension: ExternalIntelligenceDimension):
    return [o for o in result.observations if o.dimension is dimension]


def test_abstains_with_no_observations(now: datetime) -> None:
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [], currency="USD", analysis_time=now, config=CONFIG)
    assert result.status is ExternalIntelligenceOutcome.ABSTAINED


def test_policy_rate_rising(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=Decimal("4.00"))
    current = _policy(now, value=Decimal("4.25"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="USD", analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.POLICY_RATE_TREND)
    assert trends[0].value == RateTrend.RISING.value


def test_policy_rate_falling(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=Decimal("4.50"))
    current = _policy(now, value=Decimal("4.00"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="USD", analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.POLICY_RATE_TREND)
    assert trends[0].value == RateTrend.FALLING.value


def test_policy_rate_unchanged_exact_zero(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=Decimal("4.25"))
    current = _policy(now, value=Decimal("4.25"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="USD", analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.POLICY_RATE_TREND)
    assert trends[0].value == RateTrend.UNCHANGED.value


def test_single_policy_rate_observation_produces_no_trend(now: datetime) -> None:
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([_policy(now)], [], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.POLICY_RATE_TREND) == []


def test_yield_trend_rising(now: datetime) -> None:
    previous = _yield_obs(now - timedelta(days=30), value=Decimal("3.8"))
    current = _yield_obs(now, value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [previous, current], currency="USD", analysis_time=now, config=CONFIG)
    trends = _dims(result, ExternalIntelligenceDimension.YIELD_TREND)
    assert trends[0].value == RateTrend.RISING.value


def test_curve_slope_normal(now: datetime) -> None:
    short = _yield_obs(now, provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("3.5"))
    long = _yield_obs(now, provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [short, long], currency="USD", analysis_time=now, config=CONFIG)
    slopes = _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE)
    assert slopes[0].value == CurveSlopeState.NORMAL.value


def test_curve_slope_inverted(now: datetime) -> None:
    short = _yield_obs(now, provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("4.5"))
    long = _yield_obs(now, provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [short, long], currency="USD", analysis_time=now, config=CONFIG)
    slopes = _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE)
    assert slopes[0].value == CurveSlopeState.INVERTED.value


def test_curve_slope_flat_exact_zero(now: datetime) -> None:
    short = _yield_obs(now, provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("4.0"))
    long = _yield_obs(now, provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [short, long], currency="USD", analysis_time=now, config=CONFIG)
    slopes = _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE)
    assert slopes[0].value == CurveSlopeState.FLAT.value


def test_curve_slope_requires_same_provider(now: datetime) -> None:
    """Different providers reporting the same tenors are never compared -
    only same-provider compatible observations form a curve."""
    short = _yield_obs(now, provider="providerA", provider_series_id="a-2y", tenor=Tenor.of_years(2), value=Decimal("3.5"))
    long = _yield_obs(now, provider="providerB", provider_series_id="b-10y", tenor=Tenor.of_years(10), value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [short, long], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE) == []


def test_curve_slope_trend_steepening(now: datetime) -> None:
    short_t1 = _yield_obs(now - timedelta(days=30), provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("4.0"))
    long_t1 = _yield_obs(now - timedelta(days=30), provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.1"))
    short_t2 = _yield_obs(now, provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("3.5"))
    long_t2 = _yield_obs(now, provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.2"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze(
        [], [short_t1, long_t1, short_t2, long_t2], currency="USD", analysis_time=now, config=CONFIG
    )
    trends = _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE_TREND)
    assert trends[0].value == CurveSlopeTrend.STEEPENING.value


def test_curve_slope_trend_flattening(now: datetime) -> None:
    short_t1 = _yield_obs(now - timedelta(days=30), provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("3.5"))
    long_t1 = _yield_obs(now - timedelta(days=30), provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.2"))
    short_t2 = _yield_obs(now, provider_series_id="us-2y", tenor=Tenor.of_years(2), value=Decimal("4.0"))
    long_t2 = _yield_obs(now, provider_series_id="us-10y", tenor=Tenor.of_years(10), value=Decimal("4.1"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze(
        [], [short_t1, long_t1, short_t2, long_t2], currency="USD", analysis_time=now, config=CONFIG
    )
    trends = _dims(result, ExternalIntelligenceDimension.CURVE_SLOPE_TREND)
    assert trends[0].value == CurveSlopeTrend.FLATTENING.value


def test_real_nominal_relationship_nominal_above_real(now: datetime) -> None:
    nominal = _yield_obs(now, yield_type=GovernmentYieldType.NOMINAL, provider_series_id="us-10y-nom", value=Decimal("4.0"))
    real = _yield_obs(now, yield_type=GovernmentYieldType.REAL, provider_series_id="us-10y-real", value=Decimal("1.5"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [nominal, real], currency="USD", analysis_time=now, config=CONFIG)
    relationships = _dims(result, ExternalIntelligenceDimension.REAL_NOMINAL_RELATIONSHIP)
    assert relationships[0].value == RealNominalRelationship.NOMINAL_ABOVE_REAL.value


def test_real_nominal_relationship_at_parity_exact_zero(now: datetime) -> None:
    nominal = _yield_obs(now, yield_type=GovernmentYieldType.NOMINAL, provider_series_id="us-10y-nom", value=Decimal("2.0"))
    real = _yield_obs(now, yield_type=GovernmentYieldType.REAL, provider_series_id="us-10y-real", value=Decimal("2.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [nominal, real], currency="USD", analysis_time=now, config=CONFIG)
    relationships = _dims(result, ExternalIntelligenceDimension.REAL_NOMINAL_RELATIONSHIP)
    assert relationships[0].value == RealNominalRelationship.AT_PARITY.value


def test_missing_real_yield_omits_relationship(now: datetime) -> None:
    nominal = _yield_obs(now, yield_type=GovernmentYieldType.NOMINAL, value=Decimal("4.0"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([], [nominal], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.REAL_NOMINAL_RELATIONSHIP) == []


def test_missing_values_are_excluded_not_zeroed(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=None)
    current = _policy(now, value=Decimal("4.25"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="USD", analysis_time=now, config=CONFIG)
    assert _dims(result, ExternalIntelligenceDimension.POLICY_RATE_TREND) == []


def test_no_partial_quality_ever_emitted(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=Decimal("4.00"))
    current = _policy(now, value=Decimal("4.25"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="USD", analysis_time=now, config=CONFIG)
    for observation in result.observations:
        assert observation.quality is not FeatureQuality.PARTIAL


def test_result_scope_is_currency_only(now: datetime) -> None:
    previous = _policy(now - timedelta(days=30), value=Decimal("4.00"))
    current = _policy(now, value=Decimal("4.25"))
    analyst = RatesYieldAnalyst()
    result = analyst.analyze([previous, current], [], currency="EUR", analysis_time=now, config=CONFIG)
    assert result.currency == "EUR"
    assert result.symbol is None
    assert result.asset is None
    assert result.network is None
