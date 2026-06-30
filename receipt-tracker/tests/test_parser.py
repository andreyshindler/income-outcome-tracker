"""Unit tests for the OCR-text parsing helpers (no external deps)."""
import pytest

from app.parser import _parse_number, extract_amount, extract_date, extract_vendor


@pytest.mark.parametrize(
    "token,expected",
    [
        ("1,234.56", 1234.56),   # comma thousands + dot decimal
        ("1.234,56", 1234.56),   # dot thousands + comma decimal (EU)
        ("12,50", 12.5),         # decimal comma
        ("1,234", 1234.0),       # comma thousands, no decimals
        ("50", 50.0),            # bare integer
        ("50.00", 50.0),         # dot decimal
        ("1.234.567", 1234567.0),  # multiple dot thousands groups
    ],
)
def test_parse_number(token, expected):
    value, _ = _parse_number(token)
    assert value == expected


def test_amount_prefers_total_line_with_thousands_separator():
    text = 'Item A 4.56\nItem B 99.90\nסה"כ 1,234.56'
    assert extract_amount(text) == 1234.56


def test_amount_detects_whole_number_total():
    assert extract_amount("Total 50") == 50.0


def test_amount_fallback_prefers_decimals_over_phone_number():
    # No total keyword: the money figure (89.90) must win over the phone number.
    assert extract_amount("Tel 0501234567\nThanks 89.90") == 89.9


def test_amount_none_when_no_numbers():
    assert extract_amount("no digits here") is None


def test_extract_date_four_and_two_digit_years():
    assert extract_date("Date: 01/02/2026") == "2026-02-01"
    assert extract_date("07.03.24") == "2024-03-07"


def test_extract_date_invalid_returns_none():
    assert extract_date("99/99/2026") is None


def test_extract_vendor_skips_pure_numbers():
    assert extract_vendor("12345\nVeloGrip Ltd\n01/02/2026") == "VeloGrip Ltd"
