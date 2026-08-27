"""``PolicyRateProvider``/``GovernmentYieldProvider`` protocol shape: sync, runtime_checkable, narrow."""

from __future__ import annotations

import inspect
from datetime import datetime

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import GovernmentYieldType
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor
from app.rates.protocols import (
    DEFAULT_OBSERVATION_LIMIT,
    GovernmentYieldProvider,
    PolicyRateProvider,
)


class _FakePolicyRateProvider:
    """Minimal fixture satisfying ``PolicyRateProvider`` structurally."""

    def get_policy_rate(
        self,
        central_bank: CentralBank,
        start: datetime,
        end: datetime,
        *,
        limit: int = DEFAULT_OBSERVATION_LIMIT,
    ) -> list[PolicyRateObservation]:
        return []


class _FakeGovernmentYieldProvider:
    """Minimal fixture satisfying ``GovernmentYieldProvider`` structurally."""

    def get_government_yields(
        self,
        country: str,
        tenor: Tenor,
        start: datetime,
        end: datetime,
        *,
        yield_type: GovernmentYieldType = GovernmentYieldType.NOMINAL,
        limit: int = DEFAULT_OBSERVATION_LIMIT,
    ) -> list[GovernmentYieldObservation]:
        return []


class _NotAProvider:
    pass


def test_fake_policy_rate_provider_satisfies_protocol_structurally() -> None:
    assert isinstance(_FakePolicyRateProvider(), PolicyRateProvider)


def test_fake_government_yield_provider_satisfies_protocol_structurally() -> None:
    assert isinstance(_FakeGovernmentYieldProvider(), GovernmentYieldProvider)


def test_unrelated_object_does_not_satisfy_either_protocol() -> None:
    assert not isinstance(_NotAProvider(), PolicyRateProvider)
    assert not isinstance(_NotAProvider(), GovernmentYieldProvider)


def test_a_policy_rate_provider_does_not_also_satisfy_the_yield_protocol() -> None:
    assert not isinstance(_FakePolicyRateProvider(), GovernmentYieldProvider)


def test_a_government_yield_provider_does_not_also_satisfy_the_policy_rate_protocol() -> None:
    assert not isinstance(_FakeGovernmentYieldProvider(), PolicyRateProvider)


def test_get_policy_rate_is_synchronous_not_a_coroutine_function() -> None:
    assert not inspect.iscoroutinefunction(PolicyRateProvider.get_policy_rate)
    assert not inspect.iscoroutinefunction(_FakePolicyRateProvider.get_policy_rate)


def test_get_government_yields_is_synchronous_not_a_coroutine_function() -> None:
    assert not inspect.iscoroutinefunction(GovernmentYieldProvider.get_government_yields)
    assert not inspect.iscoroutinefunction(_FakeGovernmentYieldProvider.get_government_yields)


def test_default_observation_limit_is_a_positive_int() -> None:
    assert isinstance(DEFAULT_OBSERVATION_LIMIT, int)
    assert DEFAULT_OBSERVATION_LIMIT > 0


def test_policy_rate_protocol_has_exactly_one_capability_method() -> None:
    public_methods = [
        name for name, value in vars(PolicyRateProvider).items() if not name.startswith("_") and callable(value)
    ]
    assert public_methods == ["get_policy_rate"]


def test_government_yield_protocol_has_exactly_one_capability_method() -> None:
    public_methods = [
        name
        for name, value in vars(GovernmentYieldProvider).items()
        if not name.startswith("_") and callable(value)
    ]
    assert public_methods == ["get_government_yields"]


def test_no_single_god_rates_provider_protocol_exists() -> None:
    import app.rates.protocols as protocols_module

    assert not hasattr(protocols_module, "RatesProvider")
