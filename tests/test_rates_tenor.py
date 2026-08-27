"""``Tenor`` value-object contract: canonicalized identity, deterministic labels."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.rates import TenorUnit
from app.core.models.tenor import Tenor


def test_of_months_constructs() -> None:
    tenor = Tenor.of_months(3)
    assert tenor.value == 3
    assert tenor.unit is TenorUnit.MONTHS


def test_of_years_constructs() -> None:
    tenor = Tenor.of_years(10)
    assert tenor.value == 10
    assert tenor.unit is TenorUnit.YEARS


def test_24_months_equals_2_years() -> None:
    assert Tenor.of_months(24) == Tenor.of_years(2)


def test_12_months_equals_1_year() -> None:
    assert Tenor.of_months(12) == Tenor.of_years(1)


def test_3_months_not_equal_3_years() -> None:
    assert Tenor.of_months(3) != Tenor.of_years(3)


def test_equal_tenors_hash_identically() -> None:
    assert hash(Tenor.of_months(24)) == hash(Tenor.of_years(2))


def test_different_tenors_have_different_total_months() -> None:
    assert Tenor.of_months(3).total_months == 3
    assert Tenor.of_years(3).total_months == 36


def test_zero_months_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenor.of_months(0)


def test_negative_months_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenor.of_months(-3)


def test_zero_years_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenor.of_years(0)


def test_negative_years_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenor.of_years(-1)


@pytest.mark.parametrize(
    ("tenor", "label"),
    [
        (Tenor.of_months(3), "3M"),
        (Tenor.of_years(2), "2Y"),
        (Tenor.of_years(10), "10Y"),
        (Tenor.of_months(18), "18M"),
        (Tenor.of_months(12), "1Y"),
        (Tenor.of_months(24), "2Y"),
        (Tenor.of_years(30), "30Y"),
    ],
)
def test_label_is_deterministic(tenor: Tenor, label: str) -> None:
    assert tenor.label == label


def test_labels_agree_for_equal_tenors_constructed_differently() -> None:
    assert Tenor.of_months(24).label == Tenor.of_years(2).label == "2Y"


def test_tenor_is_frozen() -> None:
    tenor = Tenor.of_months(3)
    with pytest.raises(ValidationError):
        tenor.value = 6  # type: ignore[misc]


def test_not_equal_to_non_tenor_object() -> None:
    assert Tenor.of_months(3) != "3M"


def test_direct_construction_matches_classmethod_construction() -> None:
    assert Tenor(value=3, unit=TenorUnit.MONTHS) == Tenor.of_months(3)
