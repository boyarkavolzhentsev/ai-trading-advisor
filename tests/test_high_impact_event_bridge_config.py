"""``HighImpactEventCalendarTimezoneConfig`` validation tests (Calendar
Bridge timezone design closure)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig


def test_valid_iana_zone_accepted() -> None:
    config = HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Nicosia")
    assert config.server_timezone == "Europe/Nicosia"


def test_utc_accepted() -> None:
    assert HighImpactEventCalendarTimezoneConfig(server_timezone="UTC").server_timezone == "UTC"


def test_unknown_zone_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown server_timezone"):
        HighImpactEventCalendarTimezoneConfig(server_timezone="Not/AZone")


def test_server_timezone_has_no_default() -> None:
    assert HighImpactEventCalendarTimezoneConfig.model_fields["server_timezone"].is_required()


def test_config_is_frozen() -> None:
    config = HighImpactEventCalendarTimezoneConfig(server_timezone="UTC")
    with pytest.raises(ValidationError):
        config.server_timezone = "Asia/Tokyo"  # type: ignore[misc]


def test_empty_string_rejected() -> None:
    with pytest.raises(ValidationError):
        HighImpactEventCalendarTimezoneConfig(server_timezone="")
