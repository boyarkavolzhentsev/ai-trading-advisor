"""Stage 10B ``MT5RolloverPolicyConfig`` validation: valid/invalid IANA
timezone, ``rollover_hour`` bounds, no default timezone, no
``rollover_minute`` field, frozen/extra-forbid behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.mt5_rollover import MT5RolloverPolicyConfig


def test_valid_iana_timezone_accepted() -> None:
    config = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest")
    assert config.rollover_timezone == "Europe/Bucharest"


def test_utc_timezone_accepted() -> None:
    config = MT5RolloverPolicyConfig(rollover_timezone="UTC")
    assert config.rollover_timezone == "UTC"


def test_invalid_timezone_rejected() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig(rollover_timezone="Not/A_Real_Zone")


def test_empty_timezone_rejected() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig(rollover_timezone="")


def test_rollover_hour_defaults_to_zero() -> None:
    config = MT5RolloverPolicyConfig(rollover_timezone="UTC")
    assert config.rollover_hour == 0


def test_rollover_hour_accepts_boundaries() -> None:
    assert MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0).rollover_hour == 0
    assert MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=23).rollover_hour == 23


def test_rollover_hour_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=-1)


def test_rollover_hour_rejects_above_23() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=24)


def test_no_timezone_default_required_explicitly() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig()


def test_rollover_minute_field_absent() -> None:
    assert "rollover_minute" not in MT5RolloverPolicyConfig.model_fields


def test_rollover_minute_rejected_as_extra() -> None:
    with pytest.raises(ValidationError):
        MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_minute=30)


def test_config_frozen() -> None:
    config = MT5RolloverPolicyConfig(rollover_timezone="UTC")
    with pytest.raises(ValidationError):
        config.rollover_hour = 5
