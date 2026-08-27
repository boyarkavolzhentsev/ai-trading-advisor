"""Stage 4A economic-calendar event contract.

Facts only, one revision at a time - no surprise/diff calculation, no
importance inference, no qualitative policy-stance interpretation of any
kind. That discipline is enforced structurally by
``tests/test_macro_no_trading_fields.py`` and
``tests/test_macro_no_surprise_calculation.py``, not just by convention.

``actual``/``forecast``/``previous`` are raw provider facts: ``None`` means
"not reported" (not yet released, or withheld), and a genuine ``Decimal("0")``
is always a real, valid value - the two are never conflated. Country/currency
codes are validated by shape only (ISO-style 2/3 upper-case letters); callers
must supply already-normalized casing, mirroring how ``Symbol`` requires the
venue's already-normalized casing rather than the model doing the normalizing.

Identity across revisions is ``(provider, provider_event_id,
revision_number)`` - see ``app.macro.history`` for append-only revision
handling. There is no canonical cross-provider event id in Stage 4A: the same
real-world release reported by two providers is two independent records.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.economic_calendar import (
    CentralBank,
    EconomicCategory,
    EconomicEventImportance,
    EconomicEventStatus,
)
from app.core.models.base import DomainModel, Timestamp

CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
"""ISO 3166-1 alpha-2 country code, as reported by the source provider."""

CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
"""ISO 4217 currency code, as reported by the source provider."""

_ACTUAL_REQUIRED_STATUSES = (EconomicEventStatus.RELEASED, EconomicEventStatus.REVISED)


class RateDecisionDetail(DomainModel):
    """Central-bank policy-rate facts attached to a ``RATE_DECISION`` event.

    Facts only: no qualitative policy-stance interpretation, and no computed
    rate-change magnitude - both are deferred to a future analyst stage.
    ``policy_rate_actual`` follows the same ``None``-until-known
    discipline as ``EconomicEvent.actual``, including a genuine ``Decimal("0")``
    (or a negative rate, e.g. ECB/BOJ negative-rate policy) being a valid value.
    """

    central_bank: CentralBank
    policy_rate_previous: Decimal | None = None
    policy_rate_expected: Decimal | None = None
    policy_rate_actual: Decimal | None = None
    statement_time: Timestamp | None = None
    press_conference_time: Timestamp | None = None


class EconomicEvent(DomainModel):
    """One provider-reported economic-calendar record, at one revision."""

    provider: str = Field(min_length=1)
    provider_event_id: str = Field(min_length=1)
    country: CountryCode
    currency: CurrencyCode
    category: EconomicCategory
    category_raw: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    event_time: Timestamp
    publication_time: Timestamp | None = None
    received_at: Timestamp
    actual: Decimal | None = None
    forecast: Decimal | None = None
    previous: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1)
    importance: EconomicEventImportance | None = None
    status: EconomicEventStatus
    revision_number: Annotated[int, Field(ge=0)] = 0
    rate_decision_detail: RateDecisionDetail | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_category_raw_required_for_other(self) -> Self:
        if self.category is EconomicCategory.OTHER and not self.category_raw:
            raise ValueError("category_raw is required when category is OTHER")
        return self

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> Self:
        has_actual = self.actual is not None
        if self.status in _ACTUAL_REQUIRED_STATUSES:
            if not has_actual:
                raise ValueError(f"a {self.status.value} event must carry an actual value")
        elif has_actual:
            raise ValueError(f"a {self.status.value} event must not carry an actual value")

        if self.status is EconomicEventStatus.REVISED:
            if self.revision_number == 0:
                raise ValueError("a REVISED event must have revision_number > 0")
        elif self.revision_number != 0:
            raise ValueError(f"a {self.status.value} event must have revision_number == 0")
        return self

    @model_validator(mode="after")
    def _validate_rate_decision_detail_attachment(self) -> Self:
        if self.category is EconomicCategory.RATE_DECISION:
            if self.rate_decision_detail is None:
                raise ValueError("category RATE_DECISION requires rate_decision_detail")
        elif self.rate_decision_detail is not None:
            raise ValueError("rate_decision_detail is only valid for category RATE_DECISION")
        return self

    @model_validator(mode="after")
    def _validate_rate_decision_actual_consistency(self) -> Self:
        if self.rate_decision_detail is None:
            return self
        detail_has_actual = self.rate_decision_detail.policy_rate_actual is not None
        if detail_has_actual != (self.actual is not None):
            raise ValueError(
                "rate_decision_detail.policy_rate_actual and actual must both be set or both be unset"
            )
        return self


__all__ = ["CountryCode", "CurrencyCode", "EconomicEvent", "RateDecisionDetail"]
