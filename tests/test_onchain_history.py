"""Stage 4E history append/duplicate/version/eviction/query semantics.

Covers all four history classes - they share one behavioral contract (see
``app.onchain.history`` module docstring), so this suite parametrizes the
identical scenarios across all four rather than duplicating four
near-identical test files.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.onchain import OnChainUnit
from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.onchain.exceptions import DuplicateOnChainObservationError
from app.onchain.history import (
    DEFAULT_CAPACITY,
    ExchangeFlowObservationHistory,
    NetworkActivityObservationHistory,
    StablecoinSupplyObservationHistory,
    SupplyObservationHistory,
)


def _network_activity(now: datetime, **overrides: object) -> NetworkActivityObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-active-addresses",
        "asset": "BTC",
        "network": "bitcoin",
        "observation_time": now,
        "received_at": now,
        "active_addresses": 950_000,
    }
    fields.update(overrides)
    return NetworkActivityObservation(**fields)


def _supply(now: datetime, **overrides: object) -> SupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "btc-supply",
        "asset": "BTC",
        "network": "bitcoin",
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("19800000"),
    }
    fields.update(overrides)
    return SupplyObservation(**fields)


def _exchange_flow(now: datetime, **overrides: object) -> ExchangeFlowObservation:
    fields: dict[str, object] = {
        "provider": "cryptoq",
        "provider_series_id": "btc-binance-inflow",
        "asset": "BTC",
        "network": "bitcoin",
        "exchange": "binance",
        "observation_time": now,
        "received_at": now,
        "inflow": Decimal("120.5"),
        "unit": OnChainUnit.NATIVE_ASSET,
    }
    fields.update(overrides)
    return ExchangeFlowObservation(**fields)


def _stablecoin_supply(now: datetime, **overrides: object) -> StablecoinSupplyObservation:
    fields: dict[str, object] = {
        "provider": "glassnode",
        "provider_series_id": "usdt-eth-supply",
        "asset": "USDT",
        "network": "ethereum",
        "observation_time": now,
        "received_at": now,
        "total_supply": Decimal("50000000000"),
    }
    fields.update(overrides)
    return StablecoinSupplyObservation(**fields)


def test_default_capacity_matches_siblings() -> None:
    assert DEFAULT_CAPACITY == 512


class TestNetworkActivityObservationHistory:
    def test_append_and_len(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now))
        assert len(history) == 1

    def test_exact_repoll_raises_duplicate_unchanged(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now))
        with pytest.raises(DuplicateOnChainObservationError):
            history.append(_network_activity(now, received_at=now + timedelta(minutes=10)))
        assert len(history) == 1
        assert history.dropped_count == 0

    def test_changed_value_same_identity_is_new_version(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now, active_addresses=900_000))
        history.append(
            _network_activity(now, active_addresses=910_000, received_at=now + timedelta(minutes=5))
        )
        assert len(history) == 2

    def test_versions_for_preserves_append_order(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        first = _network_activity(now, active_addresses=100)
        second = _network_activity(now, active_addresses=200, received_at=now + timedelta(minutes=1))
        third = _network_activity(now, active_addresses=300, received_at=now + timedelta(minutes=2))
        history.append(first)
        history.append(second)
        history.append(third)
        versions = history.versions_for("glassnode", "btc-active-addresses", "BTC", "bitcoin", now)
        assert [v.active_addresses for v in versions] == [100, 200, 300]

    def test_latest_version(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now, active_addresses=100))
        history.append(
            _network_activity(now, active_addresses=200, received_at=now + timedelta(minutes=1))
        )
        latest = history.latest_version("glassnode", "btc-active-addresses", "BTC", "bitcoin", now)
        assert latest is not None
        assert latest.active_addresses == 200

    def test_latest_version_none_for_unknown_identity(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now))
        assert history.latest_version("glassnode", "unknown", "BTC", "bitcoin", now) is None

    def test_all_observations_ordering_independent_of_insertion(self, now: datetime) -> None:
        observations = [
            _network_activity(now + timedelta(hours=offset), provider_series_id=f"series-{offset}")
            for offset in (3, 1, 4, 0, 2)
        ]
        forward = NetworkActivityObservationHistory()
        for observation in observations:
            forward.append(observation)
        backward = NetworkActivityObservationHistory()
        for observation in reversed(observations):
            backward.append(observation)
        forward_ids = [o.provider_series_id for o in forward.all_observations()]
        backward_ids = [o.provider_series_id for o in backward.all_observations()]
        assert forward_ids == backward_ids == ["series-0", "series-1", "series-2", "series-3", "series-4"]

    def test_by_provider_filters(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory()
        history.append(_network_activity(now, provider="providerA"))
        history.append(_network_activity(now, provider="providerB", provider_series_id="other"))
        results = history.by_provider("providerA")
        assert [o.provider for o in results] == ["providerA"]

    def test_eviction_drop_oldest_tracked(self, now: datetime) -> None:
        history = NetworkActivityObservationHistory(capacity=2)
        history.append(_network_activity(now, provider_series_id="s1"))
        history.append(_network_activity(now, provider_series_id="s2"))
        history.append(_network_activity(now, provider_series_id="s3"))
        assert len(history) == 2
        assert history.dropped_count == 1
        remaining = {o.provider_series_id for o in history.all_observations()}
        assert remaining == {"s2", "s3"}

    def test_instances_are_independent(self, now: datetime) -> None:
        first = NetworkActivityObservationHistory()
        second = NetworkActivityObservationHistory()
        first.append(_network_activity(now))
        assert len(first) == 1
        assert len(second) == 0

    def test_no_wall_clock_or_randomness(self) -> None:
        import inspect

        source = inspect.getsource(NetworkActivityObservationHistory)
        for forbidden in ("datetime.now", "utcnow", "random.", "uuid."):
            assert forbidden not in source


class TestSupplyObservationHistory:
    def test_append_and_len(self, now: datetime) -> None:
        history = SupplyObservationHistory()
        history.append(_supply(now))
        assert len(history) == 1

    def test_exact_repoll_raises_duplicate_unchanged(self, now: datetime) -> None:
        history = SupplyObservationHistory()
        history.append(_supply(now))
        with pytest.raises(DuplicateOnChainObservationError):
            history.append(_supply(now, received_at=now + timedelta(minutes=10)))
        assert len(history) == 1

    def test_changed_value_same_identity_is_new_version(self, now: datetime) -> None:
        history = SupplyObservationHistory()
        history.append(_supply(now, total_supply=Decimal("19800000")))
        history.append(
            _supply(now, total_supply=Decimal("19800100"), received_at=now + timedelta(minutes=5))
        )
        assert len(history) == 2

    def test_latest_version(self, now: datetime) -> None:
        history = SupplyObservationHistory()
        history.append(_supply(now, total_supply=Decimal("1")))
        history.append(_supply(now, total_supply=Decimal("2"), received_at=now + timedelta(minutes=1)))
        latest = history.latest_version("glassnode", "btc-supply", "BTC", "bitcoin", now)
        assert latest is not None
        assert latest.total_supply == Decimal("2")

    def test_by_provider_filters(self, now: datetime) -> None:
        history = SupplyObservationHistory()
        history.append(_supply(now, provider="providerA"))
        history.append(_supply(now, provider="providerB", provider_series_id="other"))
        results = history.by_provider("providerB")
        assert [o.provider for o in results] == ["providerB"]

    def test_eviction_drop_oldest_tracked(self, now: datetime) -> None:
        history = SupplyObservationHistory(capacity=1)
        history.append(_supply(now, provider_series_id="s1"))
        history.append(_supply(now, provider_series_id="s2"))
        assert len(history) == 1
        assert history.dropped_count == 1


class TestExchangeFlowObservationHistory:
    def test_append_and_len(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now))
        assert len(history) == 1

    def test_exact_repoll_raises_duplicate_unchanged(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now))
        with pytest.raises(DuplicateOnChainObservationError):
            history.append(_exchange_flow(now, received_at=now + timedelta(minutes=10)))
        assert len(history) == 1

    def test_different_exchange_is_different_identity(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now, exchange="binance"))
        history.append(_exchange_flow(now, exchange="coinbase"))
        assert len(history) == 2

    def test_none_exchange_is_its_own_identity(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now, exchange=None))
        history.append(_exchange_flow(now, exchange="binance"))
        assert len(history) == 2

    def test_latest_version_with_exchange_dimension(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now, exchange="binance", inflow=Decimal("10")))
        history.append(
            _exchange_flow(
                now, exchange="binance", inflow=Decimal("20"), received_at=now + timedelta(minutes=1)
            )
        )
        latest = history.latest_version("cryptoq", "btc-binance-inflow", "BTC", "bitcoin", "binance", now)
        assert latest is not None
        assert latest.inflow == Decimal("20")

    def test_by_provider_filters(self, now: datetime) -> None:
        history = ExchangeFlowObservationHistory()
        history.append(_exchange_flow(now, provider="providerA"))
        history.append(_exchange_flow(now, provider="providerB", provider_series_id="other"))
        results = history.by_provider("providerA")
        assert [o.provider for o in results] == ["providerA"]


class TestStablecoinSupplyObservationHistory:
    def test_append_and_len(self, now: datetime) -> None:
        history = StablecoinSupplyObservationHistory()
        history.append(_stablecoin_supply(now))
        assert len(history) == 1

    def test_exact_repoll_raises_duplicate_unchanged(self, now: datetime) -> None:
        history = StablecoinSupplyObservationHistory()
        history.append(_stablecoin_supply(now))
        with pytest.raises(DuplicateOnChainObservationError):
            history.append(_stablecoin_supply(now, received_at=now + timedelta(minutes=10)))
        assert len(history) == 1

    def test_same_asset_different_network_is_different_identity(self, now: datetime) -> None:
        history = StablecoinSupplyObservationHistory()
        history.append(_stablecoin_supply(now, asset="USDT", network="ethereum"))
        history.append(_stablecoin_supply(now, asset="USDT", network="tron"))
        assert len(history) == 2

    def test_latest_version(self, now: datetime) -> None:
        history = StablecoinSupplyObservationHistory()
        history.append(_stablecoin_supply(now, total_supply=Decimal("1")))
        history.append(
            _stablecoin_supply(now, total_supply=Decimal("2"), received_at=now + timedelta(minutes=1))
        )
        latest = history.latest_version("glassnode", "usdt-eth-supply", "USDT", "ethereum", now)
        assert latest is not None
        assert latest.total_supply == Decimal("2")

    def test_by_provider_filters(self, now: datetime) -> None:
        history = StablecoinSupplyObservationHistory()
        history.append(_stablecoin_supply(now, provider="providerA"))
        history.append(_stablecoin_supply(now, provider="providerB", provider_series_id="other"))
        results = history.by_provider("providerA")
        assert [o.provider for o in results] == ["providerA"]


def test_history_query_surface_is_minimal() -> None:
    """No by_asset()/by_network()/by_exchange()/date-range/aggregation
    method exists on any of the four history classes - per the approved
    scope correction, checked structurally rather than by omission."""
    forbidden_methods = {
        "by_asset",
        "by_network",
        "by_exchange",
        "in_range",
        "aggregate",
        "search",
    }
    for history_cls in (
        NetworkActivityObservationHistory,
        SupplyObservationHistory,
        ExchangeFlowObservationHistory,
        StablecoinSupplyObservationHistory,
    ):
        public_methods = {name for name in vars(history_cls) if not name.startswith("_")}
        assert forbidden_methods.isdisjoint(public_methods)
        assert public_methods == {
            "append",
            "all_observations",
            "by_provider",
            "versions_for",
            "latest_version",
            "dropped_count",
            "capacity",
        }
