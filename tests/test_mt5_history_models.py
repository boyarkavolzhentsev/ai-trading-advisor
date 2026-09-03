"""Stage 10D ``MT5Deal``/``MT5RealizedDailyPnLAssessment`` model validation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.models.mt5_history import MT5Deal, MT5RealizedDailyPnLAssessment
from tests.mt5_history_support import NOW, default_deal

# --- MT5Deal ---


def test_deal_rejects_non_positive_ticket() -> None:
    with pytest.raises(ValidationError):
        default_deal(ticket=0)


def test_deal_accepts_zero_order_and_position_id() -> None:
    deal = default_deal(order=0, position_id=0)
    assert deal.order == 0
    assert deal.position_id == 0


def test_deal_rejects_negative_order() -> None:
    with pytest.raises(ValidationError):
        default_deal(order=-1)


def test_deal_symbol_may_be_none() -> None:
    deal = default_deal(symbol=None, deal_type=MT5DealType.NON_TRADING)
    assert deal.symbol is None


def test_deal_volume_price_may_be_zero() -> None:
    deal = default_deal(volume=Decimal("0"), price=Decimal("0"), deal_type=MT5DealType.NON_TRADING)
    assert deal.volume == Decimal("0")
    assert deal.price == Decimal("0")


def test_deal_monetary_fields_may_be_negative_and_are_not_abs() -> None:
    deal = default_deal(profit=Decimal("-50"), commission=Decimal("-5"), swap=Decimal("-1"), fee=Decimal("-2"))
    assert deal.profit == Decimal("-50")
    assert deal.commission == Decimal("-5")
    assert deal.swap == Decimal("-1")
    assert deal.fee == Decimal("-2")


def test_deal_frozen() -> None:
    deal = default_deal()
    with pytest.raises(ValidationError):
        deal.profit = Decimal("1")


def test_deal_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5Deal(
            ticket=1,
            order=1,
            position_id=1,
            time=NOW,
            symbol="EURUSD",
            deal_type=MT5DealType.BUY,
            entry=MT5DealEntry.OUT,
            volume=Decimal("1"),
            price=Decimal("1"),
            profit=Decimal("0"),
            commission=Decimal("0"),
            swap=Decimal("0"),
            fee=Decimal("0"),
            magic=1,
        )


def test_deal_has_no_speculative_fields() -> None:
    for field in ("reason", "comment", "magic", "external_id"):
        assert field not in MT5Deal.model_fields


# --- MT5RealizedDailyPnLAssessment ---


def test_assessment_ready_requires_pnl() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(as_of=NOW, trading_day_key="2026-01-01", outcome=MT5RealizedPnLOutcome.READY)


def test_assessment_ready_must_not_carry_reasons() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(
            as_of=NOW,
            trading_day_key="2026-01-01",
            outcome=MT5RealizedPnLOutcome.READY,
            realized_daily_pnl=Decimal("0"),
            blocked_reasons=(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE,),
        )


def test_assessment_blocked_must_not_carry_pnl() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(
            as_of=NOW,
            trading_day_key="2026-01-01",
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            realized_daily_pnl=Decimal("0"),
            blocked_reasons=(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE,),
            unsafe_deal_tickets=(1,),
        )


def test_assessment_blocked_requires_reasons_and_tickets() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(as_of=NOW, trading_day_key="2026-01-01", outcome=MT5RealizedPnLOutcome.BLOCKED)


def test_assessment_rejects_non_canonical_reason_order() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(
            as_of=NOW,
            trading_day_key="2026-01-01",
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=(MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE, MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP),
            unsafe_deal_tickets=(1,),
        )


def test_assessment_rejects_duplicate_reasons() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(
            as_of=NOW,
            trading_day_key="2026-01-01",
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=(MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP, MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP),
            unsafe_deal_tickets=(1,),
        )


def test_assessment_rejects_duplicate_unsafe_tickets() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(
            as_of=NOW,
            trading_day_key="2026-01-01",
            outcome=MT5RealizedPnLOutcome.BLOCKED,
            blocked_reasons=(MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP,),
            unsafe_deal_tickets=(1, 1),
        )


def test_assessment_rejects_malformed_trading_day_key() -> None:
    with pytest.raises(ValidationError):
        MT5RealizedDailyPnLAssessment(as_of=NOW, trading_day_key="not-a-date", outcome=MT5RealizedPnLOutcome.READY, realized_daily_pnl=Decimal("0"))


def test_assessment_ready_zero_is_valid() -> None:
    assessment = MT5RealizedDailyPnLAssessment(
        as_of=NOW, trading_day_key="2026-01-01", outcome=MT5RealizedPnLOutcome.READY, realized_daily_pnl=Decimal("0")
    )
    assert assessment.realized_daily_pnl == Decimal("0")


def test_assessment_frozen() -> None:
    assessment = MT5RealizedDailyPnLAssessment(
        as_of=NOW, trading_day_key="2026-01-01", outcome=MT5RealizedPnLOutcome.READY, realized_daily_pnl=Decimal("0")
    )
    with pytest.raises(ValidationError):
        assessment.realized_daily_pnl = Decimal("1")
