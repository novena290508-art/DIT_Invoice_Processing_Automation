"""Unit tests for src/validator.py."""

import pandas as pd

from src.validator import (
    ZERO_VALUE_WARNING,
    parse_numeric_amount,
    parse_valid_date,
    validate_dataframe,
    validate_invoice_row,
)


def _base_row(**overrides):
    row = {
        "invoice_number": "INV-2026-001",
        "vendor_name": "Apex Office Supplies",
        "invoice_date": "2026-10-01",
        "subtotal": "1000.00",
        "tax_amount": "180.00",
        "total_amount": "1180.00",
        "currency": "INR",
    }
    row.update(overrides)
    return row


def test_valid_invoice_record():
    result = validate_invoice_row(_base_row(), row_index=1)
    assert result["is_valid"] is True
    assert result["has_warning"] is False
    assert result["validation_status"] == "VALID"
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["parsed_date"] == "2026-10-01"
    assert result["currency"] == "INR"


def test_missing_required_fields():
    missing_inv = validate_invoice_row(_base_row(invoice_number=""), row_index=1)
    assert missing_inv["is_valid"] is False
    assert missing_inv["validation_status"] == "INVALID"
    assert any("invoice_number" in err for err in missing_inv["errors"])

    missing_vendor = validate_invoice_row(_base_row(vendor_name="   "), row_index=2)
    assert missing_vendor["is_valid"] is False
    assert any("vendor_name" in err for err in missing_vendor["errors"])


def test_invalid_invoice_dates():
    assert parse_valid_date("2026-13-45") is None
    assert parse_valid_date("invalid-date") is None

    res = validate_invoice_row(_base_row(invoice_date="2026-13-45"), row_index=1)
    assert res["is_valid"] is False
    assert res["parsed_date"] is None
    assert any("invoice_date" in err for err in res["errors"])


def test_non_numeric_amounts():
    assert parse_numeric_amount("ABC") is None
    assert parse_numeric_amount("N/A") is None

    for field, bad_val in [("subtotal", "ABC"), ("tax_amount", "N/A"), ("total_amount", "TBD")]:
        res = validate_invoice_row(_base_row(**{field: bad_val}), row_index=1)
        assert res["is_valid"] is False
        assert any(f"Non-numeric {field}" in err for err in res["errors"])


def test_incorrect_total_calculation():
    res = validate_invoice_row(
        _base_row(subtotal="2000.00", tax_amount="360.00", total_amount="2500.00"),
        row_index=1,
    )
    assert res["is_valid"] is False
    assert any("Total mismatch" in err for err in res["errors"])

    within_tolerance = validate_invoice_row(
        _base_row(subtotal="100.00", tax_amount="18.00", total_amount="118.01"),
        row_index=2,
    )
    assert within_tolerance["is_valid"] is True


def test_negative_amounts():
    res = validate_invoice_row(
        _base_row(subtotal="-100.00", tax_amount="18.00", total_amount="-82.00"),
        row_index=1,
    )
    assert res["is_valid"] is False
    assert any("Negative subtotal" in err for err in res["errors"])
    assert any("Negative total_amount" in err for err in res["errors"])


def test_zero_value_invoice_warning():
    res = validate_invoice_row(
        _base_row(subtotal="0.00", tax_amount="0.00", total_amount="0.00"),
        row_index=1,
    )
    assert res["is_valid"] is True
    assert res["has_warning"] is True
    assert res["validation_status"] == "WARNING / REVIEW REQUIRED"
    assert res["errors"] == []
    assert res["warnings"] == [ZERO_VALUE_WARNING]


def test_missing_currency_defaults_to_unknown_and_preserves_valid_row():
    df = pd.DataFrame([_base_row(currency="")])
    results = validate_dataframe(df)
    assert len(results) == 1
    assert results[0]["currency"] == "UNKNOWN"
    assert results[0]["is_valid"] is True
