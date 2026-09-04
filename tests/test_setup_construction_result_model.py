"""``CandidateTradeSetup``/``SetupConstructionResult``/``StrategySetupResult``
invariants."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.setup_construction import CandidateTradeSetup, SetupConstructionResult, StrategySetupResult
from tests.setup_construction_support import AS_OF, trend_following_policy_result

_BASE_SETUP_FIELDS: dict[str, object] = {
    "family": StrategyFamily.TREND_FOLLOWING,
    "direction": TradeDirection.LONG,
    "symbol": "BTCUSDT",
    "entry_price": Decimal("110"),
    "stop_loss": Decimal("95"),
    "take_profit_levels": (),
    "risk_per_unit": Decimal("1500"),
    "signal_time": AS_OF,
    "valid_until": AS_OF + timedelta(minutes=5),
}


def _setup(**overrides: object) -> CandidateTradeSetup:
    fields = dict(_BASE_SETUP_FIELDS)
    fields.update(overrides)
    return CandidateTradeSetup(**fields)


def test_valid_long_setup_constructs() -> None:
    setup = _setup()
    assert setup.direction is TradeDirection.LONG


def test_neutral_direction_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _setup(direction=TradeDirection.NEUTRAL)


def test_wait_direction_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _setup(direction=TradeDirection.WAIT)


def test_long_stop_not_below_entry_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _setup(direction=TradeDirection.LONG, entry_price=Decimal("100"), stop_loss=Decimal("100"))


def test_short_stop_not_above_entry_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _setup(direction=TradeDirection.SHORT, entry_price=Decimal("100"), stop_loss=Decimal("99"))


def test_valid_until_not_after_signal_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _setup(signal_time=AS_OF, valid_until=AS_OF)


def test_constructed_without_setup_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(family=StrategyFamily.TREND_FOLLOWING, outcome=SetupConstructionOutcome.CONSTRUCTED, setup=None)


def test_constructed_with_reasons_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=SetupConstructionOutcome.CONSTRUCTED,
            setup=_setup(),
            reasons=(SetupBlockReason.MISSING_STOP_REFERENCE,),
        )


def test_blocked_with_setup_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=SetupConstructionOutcome.BLOCKED,
            setup=_setup(),
            reasons=(SetupBlockReason.MISSING_STOP_REFERENCE,),
        )


def test_blocked_with_zero_reasons_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(family=StrategyFamily.TREND_FOLLOWING, outcome=SetupConstructionOutcome.BLOCKED, reasons=())


def test_blocked_with_two_reasons_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(
            family=StrategyFamily.TREND_FOLLOWING,
            outcome=SetupConstructionOutcome.BLOCKED,
            reasons=(SetupBlockReason.MISSING_STOP_REFERENCE, SetupBlockReason.INVALID_STOP_SIDE),
        )


def test_setup_family_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SetupConstructionResult(
            family=StrategyFamily.BREAKOUT,
            outcome=SetupConstructionOutcome.CONSTRUCTED,
            setup=_setup(family=StrategyFamily.TREND_FOLLOWING),
        )


def test_strategy_setup_result_requires_exact_policy_eligible_family_coverage() -> None:
    policy = trend_following_policy_result(direction="UPWARD")  # only TREND_FOLLOWING is eligible
    correct = SetupConstructionResult(
        family=StrategyFamily.TREND_FOLLOWING, outcome=SetupConstructionOutcome.BLOCKED, reasons=(SetupBlockReason.SHARED_FACT_UNAVAILABLE,)
    )
    StrategySetupResult(strategy_policy_result=policy, family_results=(correct,))  # must not raise


def test_strategy_setup_result_rejects_a_family_outside_policy_eligibility() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    wrong_family = SetupConstructionResult(
        family=StrategyFamily.EVENT_DRIVEN, outcome=SetupConstructionOutcome.BLOCKED, reasons=(SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)
    )
    with pytest.raises(ValidationError):
        StrategySetupResult(strategy_policy_result=policy, family_results=(wrong_family,))


def test_strategy_setup_result_rejects_missing_eligible_family_coverage() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    with pytest.raises(ValidationError):
        StrategySetupResult(strategy_policy_result=policy, family_results=())
