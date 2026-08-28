"""Stage 4F analyst configuration: immutability, no silent defaults."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.external_intelligence_analysts.config import (
    MacroAnalystConfig,
    NewsSentimentAnalystConfig,
    OnChainAnalystConfig,
    RatesYieldAnalystConfig,
)


def test_macro_config_requires_explicit_values() -> None:
    with pytest.raises(ValidationError):
        MacroAnalystConfig()  # type: ignore[call-arg]


def test_macro_config_no_default_values() -> None:
    assert MacroAnalystConfig.model_fields["proximity_window"].is_required()
    assert MacroAnalystConfig.model_fields["staleness_threshold"].is_required()


def test_macro_config_is_frozen() -> None:
    config = MacroAnalystConfig(proximity_window=timedelta(hours=24), staleness_threshold=timedelta(hours=6))
    with pytest.raises(ValidationError):
        config.proximity_window = timedelta(hours=1)  # type: ignore[misc]


def test_rates_yield_config_requires_explicit_value() -> None:
    with pytest.raises(ValidationError):
        RatesYieldAnalystConfig()  # type: ignore[call-arg]


def test_rates_yield_config_has_only_staleness_threshold() -> None:
    assert set(RatesYieldAnalystConfig.model_fields) == {"staleness_threshold"}


def test_news_sentiment_config_requires_explicit_values() -> None:
    with pytest.raises(ValidationError):
        NewsSentimentAnalystConfig()  # type: ignore[call-arg]


def test_news_sentiment_config_is_frozen() -> None:
    config = NewsSentimentAnalystConfig(recency_window=timedelta(hours=24), staleness_threshold=timedelta(hours=6))
    with pytest.raises(ValidationError):
        config.recency_window = timedelta(hours=1)  # type: ignore[misc]


def test_on_chain_config_requires_explicit_value() -> None:
    with pytest.raises(ValidationError):
        OnChainAnalystConfig()  # type: ignore[call-arg]


def test_on_chain_config_has_only_staleness_threshold() -> None:
    assert set(OnChainAnalystConfig.model_fields) == {"staleness_threshold"}


def test_no_config_has_a_giant_shared_shape() -> None:
    """No config model exceeds two fields - a deliberately small, per-analyst shape."""
    for config_cls in (MacroAnalystConfig, RatesYieldAnalystConfig, NewsSentimentAnalystConfig, OnChainAnalystConfig):
        assert len(config_cls.model_fields) <= 2
