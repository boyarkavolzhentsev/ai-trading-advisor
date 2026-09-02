"""Stage 10A model validation: ``MT5RuntimeStatus``, ``MT5AccountFacts``,
``MT5Credentials`` - frozen/extra-forbid behavior, Decimal monetary fields,
timezone-aware ``as_of``, and credential secret-handling."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.models.mt5_runtime import MT5AccountFacts, MT5Credentials, MT5RuntimeStatus

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NAIVE_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _account_facts(**overrides: object) -> MT5AccountFacts:
    fields: dict[str, object] = {
        "as_of": NOW,
        "equity": Decimal("100000"),
        "balance": Decimal("100000"),
        "margin": Decimal("0"),
        "margin_free": Decimal("100000"),
        "margin_level": None,
        "currency": "USD",
        "trade_allowed": True,
        "trade_expert": True,
        "margin_mode": AccountPositionMode.NETTING,
        "floating_pnl": Decimal("0"),
    }
    fields.update(overrides)
    return MT5AccountFacts(**fields)


# --- MT5RuntimeStatus ---


def test_available_forbids_reason() -> None:
    with pytest.raises(ValidationError):
        MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE, reason="should not be allowed")


def test_available_without_reason_accepted() -> None:
    status = MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE)
    assert status.reason is None


def test_non_available_may_omit_reason() -> None:
    status = MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.TERMINAL_UNAVAILABLE)
    assert status.reason is None


def test_non_available_may_carry_reason() -> None:
    status = MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.INITIALIZATION_FAILED, reason="(1, 'IPC timeout')")
    assert status.reason == "(1, 'IPC timeout')"


def test_runtime_status_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        MT5RuntimeStatus(as_of=NAIVE_NOW, state=MT5ConnectivityState.AVAILABLE)


def test_runtime_status_frozen() -> None:
    status = MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE)
    with pytest.raises(ValidationError):
        status.state = MT5ConnectivityState.ACCOUNT_UNAVAILABLE


def test_runtime_status_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE, confidence=0.9)


# --- MT5AccountFacts ---


def test_account_facts_monetary_fields_are_decimal() -> None:
    facts = _account_facts()
    assert isinstance(facts.equity, Decimal)
    assert isinstance(facts.balance, Decimal)
    assert isinstance(facts.margin, Decimal)
    assert isinstance(facts.margin_free, Decimal)


def test_account_facts_margin_level_may_be_none() -> None:
    facts = _account_facts(margin_level=None)
    assert facts.margin_level is None


def test_account_facts_margin_level_decimal_when_present() -> None:
    facts = _account_facts(margin_level=Decimal("250.5"))
    assert facts.margin_level == Decimal("250.5")


def test_account_facts_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        _account_facts(as_of=NAIVE_NOW)


def test_account_facts_rejects_empty_currency() -> None:
    with pytest.raises(ValidationError):
        _account_facts(currency="")


def test_account_facts_frozen() -> None:
    facts = _account_facts()
    with pytest.raises(ValidationError):
        facts.equity = Decimal("0")


def test_account_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MT5AccountFacts(
            as_of=NOW,
            equity=Decimal("100000"),
            balance=Decimal("100000"),
            margin=Decimal("0"),
            margin_free=Decimal("100000"),
            currency="USD",
            trade_allowed=True,
            trade_expert=True,
            margin_mode=AccountPositionMode.NETTING,
            floating_pnl=Decimal("0"),
            login=12345,
        )


def test_account_facts_floating_pnl_supports_positive_value() -> None:
    facts = _account_facts(floating_pnl=Decimal("1234.56"))
    assert facts.floating_pnl == Decimal("1234.56")


def test_account_facts_floating_pnl_supports_negative_value() -> None:
    facts = _account_facts(floating_pnl=Decimal("-987.65"))
    assert facts.floating_pnl == Decimal("-987.65")


def test_account_facts_floating_pnl_supports_legitimate_zero() -> None:
    facts = _account_facts(floating_pnl=Decimal("0"))
    assert facts.floating_pnl == Decimal("0")


def test_account_facts_floating_pnl_is_required() -> None:
    with pytest.raises(ValidationError):
        MT5AccountFacts(
            as_of=NOW,
            equity=Decimal("100000"),
            balance=Decimal("100000"),
            margin=Decimal("0"),
            margin_free=Decimal("100000"),
            currency="USD",
            trade_allowed=True,
            trade_expert=True,
            margin_mode=AccountPositionMode.NETTING,
        )


def test_account_facts_carries_no_account_identity_fields() -> None:
    assert "login" not in MT5AccountFacts.model_fields
    assert "account_number" not in MT5AccountFacts.model_fields
    assert "server" not in MT5AccountFacts.model_fields
    assert "password" not in MT5AccountFacts.model_fields


# --- MT5Credentials ---


def test_credentials_password_not_in_repr() -> None:
    credentials = MT5Credentials(login=12345, password="super-secret-value", server="Broker-Server")
    assert "super-secret-value" not in repr(credentials)
    assert "super-secret-value" not in str(credentials)


def test_credentials_password_not_in_model_dump_json() -> None:
    credentials = MT5Credentials(login=12345, password="super-secret-value", server="Broker-Server")
    assert "super-secret-value" not in credentials.model_dump_json()


def test_credentials_get_secret_value_recovers_password() -> None:
    credentials = MT5Credentials(login=12345, password="super-secret-value", server="Broker-Server")
    assert credentials.password is not None
    assert credentials.password.get_secret_value() == "super-secret-value"


def test_credentials_all_fields_optional() -> None:
    credentials = MT5Credentials()
    assert credentials.login is None
    assert credentials.password is None
    assert credentials.server is None


def test_credentials_rejects_non_positive_login() -> None:
    with pytest.raises(ValidationError):
        MT5Credentials(login=0)
