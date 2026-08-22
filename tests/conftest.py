"""Shared test fixtures.

No market data is fabricated here: values are minimal, obviously synthetic
placeholders used only to exercise validation rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.models import DataQuality


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def data_quality(now: datetime) -> DataQuality:
    return DataQuality(is_valid=True, source="test", checked_at=now)


@pytest.fixture
def price() -> Decimal:
    return Decimal("100")
