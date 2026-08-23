"""ReconnectPolicy backoff calculation."""

from __future__ import annotations

import pytest

from app.market_data.realtime.reconnect import ReconnectPolicy


def test_delay_grows_exponentially_with_max_jitter() -> None:
    # jitter's domain is [0, 1) (matching random.random()), so the practical
    # "no scaling" ceiling is jitter just under 1.0.
    policy = ReconnectPolicy(base_seconds=1.0, factor=2.0, max_seconds=60.0)
    jitter = 1.0 - 1e-9
    assert policy.delay_for_attempt(1, jitter=jitter) == pytest.approx(1.0, rel=1e-6)
    assert policy.delay_for_attempt(2, jitter=jitter) == pytest.approx(2.0, rel=1e-6)
    assert policy.delay_for_attempt(3, jitter=jitter) == pytest.approx(4.0, rel=1e-6)


def test_delay_is_capped_at_max_seconds() -> None:
    policy = ReconnectPolicy(base_seconds=1.0, factor=2.0, max_seconds=5.0)
    assert policy.delay_for_attempt(10, jitter=1.0 - 1e-9) == pytest.approx(5.0, rel=1e-6)


def test_jitter_scales_the_delay_linearly() -> None:
    policy = ReconnectPolicy(base_seconds=2.0, factor=2.0, max_seconds=60.0)
    assert policy.delay_for_attempt(1, jitter=0.5) == pytest.approx(1.0)
    assert policy.delay_for_attempt(1, jitter=0.0) == pytest.approx(0.0)


def test_rejects_non_positive_attempt() -> None:
    policy = ReconnectPolicy()
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        policy.delay_for_attempt(0, jitter=0.5)


def test_rejects_out_of_range_jitter() -> None:
    policy = ReconnectPolicy()
    with pytest.raises(ValueError, match="jitter must be in"):
        policy.delay_for_attempt(1, jitter=1.0000001)
    with pytest.raises(ValueError, match="jitter must be in"):
        policy.delay_for_attempt(1, jitter=-0.1)


@pytest.mark.parametrize(
    ("base", "factor", "max_seconds"),
    [(0.0, 2.0, 10.0), (1.0, 1.0, 10.0), (1.0, 2.0, 0.5)],
)
def test_rejects_invalid_configuration(base: float, factor: float, max_seconds: float) -> None:
    with pytest.raises(ValueError):
        ReconnectPolicy(base_seconds=base, factor=factor, max_seconds=max_seconds)
