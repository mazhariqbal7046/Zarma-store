import pytest

from app.commerce.commission import calculate_commission


def test_commission_is_exactly_ten_percent() -> None:
    assert calculate_commission(10_000) == (1_000, 9_000)


def test_commission_rounds_to_whole_pkr() -> None:
    assert calculate_commission(101) == (10, 91)


def test_commission_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        calculate_commission(-1)
