"""Stage 3A must carry no trading vocabulary as actual field/enum-member
names: no BUY/SELL/LONG/SHORT/entry/stop/target/confidence-as-signal/regime
classification anywhere in a Stage 3A model or enum's *structure*.

Deliberately structural (field names, enum member names), not a raw source-
text grep: several docstrings in this package legitimately explain what is
NOT included using exactly this vocabulary in a negative sentence (e.g. "no
bullish/bearish label"), mirroring the same house style already used in
``app.core.enums.flow_analysis``'s own module docstring. Grepping prose
would flag that legitimate documentation as if it were a violation.
"""

from __future__ import annotations

import re
from enum import StrEnum

import pytest
from pydantic import BaseModel

from app.core.enums import technical as technical_enums
from app.core.models import (
    candle_structure_features,
    market_structure_features,
    momentum_features,
    moving_average_features,
    range_state_features,
    technical_feature_snapshot,
    trend_features,
    volatility_features,
)

MODEL_MODULES = (
    candle_structure_features, market_structure_features, momentum_features,
    moving_average_features, range_state_features, technical_feature_snapshot,
    trend_features, volatility_features,
)

FORBIDDEN_PATTERNS = tuple(
    re.compile(rf"\b{term}\b", re.IGNORECASE)
    for term in (
        "buy", "sell", "long", "short", "entry", "stop", "target",
        "confidence", "recommend", "probability", "position_siz",
        "money_management", "diversification", "judge", "regime",
        "uptrend", "downtrend", "bullish", "bearish",
    )
)


def _model_classes(module) -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == module.__name__
    ]


def _enum_classes(module) -> list[type[StrEnum]]:
    return [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, StrEnum) and obj.__module__ == module.__name__
    ]


@pytest.mark.parametrize("module", MODEL_MODULES, ids=lambda m: m.__name__)
def test_no_forbidden_field_names(module) -> None:
    for model in _model_classes(module):
        for field_name in model.model_fields:
            for pattern in FORBIDDEN_PATTERNS:
                assert not pattern.search(field_name), (
                    f"{module.__name__}.{model.__name__}.{field_name} contains forbidden trading term"
                )


def test_no_forbidden_enum_member_names() -> None:
    for enum_cls in _enum_classes(technical_enums):
        for member in enum_cls:
            for pattern in FORBIDDEN_PATTERNS:
                assert not pattern.search(member.name), (
                    f"{enum_cls.__name__}.{member.name} contains forbidden trading term"
                )
                assert not pattern.search(member.value), (
                    f"{enum_cls.__name__}.{member.name} value contains forbidden trading term"
                )
