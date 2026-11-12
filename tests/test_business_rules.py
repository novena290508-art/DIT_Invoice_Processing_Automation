"""Unit tests for src/business_rules.py."""

import pandas as pd

from src.business_rules import build_duplicate_key, normalize_identifier, process_invoices


def test_normalization_helpers():
    assert normalize_identifier("  Acme   Supplies  ") == "acme supplies"
    assert build_duplicate_key("  APEX ", " inv-001 ") == ("apex", "inv-001")
    assert build_duplicate_key("", "INV-001") is None


def test_valid_and_warning_classification():
    df = pd.DataFrame([
        {
            "invoice_number": "INV-1001",
            "vendor_name": "Apex Supplies",
            "invoice_date": "2026-10-01",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
            "currency": "INR",
        },
        {
            "invoice_number": "INV-1002",
            "vendor_name": "Lakshmi Press",
            "invoice_date": "2026-10-02",
            "subtotal": "0",
            "tax_amount": "0",
            "total_amount": "0",
            "currency": "INR",
        },
    ])

    result = process_invoices(df)
    assert result["records"][0]["status"] == "Valid"
    assert result["records"][1]["status"] == "Warning"
    assert result["summary"]["valid_invoices"] == 1
    assert result["summary"]["warning_invoices"] == 1
    assert result["summary"]["invalid_invoices"] == 0
    assert len(result["warning_records"]) == 1
    assert len(result["exceptions"]) == 1


def test_exact_case_insensitive_and_whitespace_duplicate_detection():
    df = pd.DataFrame([
        {
            "invoice_number": "INV-2001",
            "vendor_name": "Bharat Logistics Pvt Ltd",
            "invoice_date": "2026-10-01",
            "subtotal": "5000.00",
            "tax_amount": "900.00",
            "total_amount": "5900.00",
            "currency": "INR",
        },
        {
            "invoice_number": "INV-2001",
            "vendor_name": "Bharat Logistics Pvt Ltd",
            "invoice_date": "2026-10-01",
            "subtotal": "5000.00",
            "tax_amount": "900.00",
            "total_amount": "5900.00",
            "currency": "INR",
        },
        {
            "invoice_number": "  inv-2001  ",
            "vendor_name": "  BHARAT LOGISTICS PVT LTD ",
            "invoice_date": "2026-10-01",
            "subtotal": "5000.00",
            "tax_amount": "900.00",
            "total_amount": "5900.00",
            "currency": "INR",
        },
    ])

    result = process_invoices(df)
    statuses = [rec["status"] for rec in result["records"]]
    assert statuses == ["Valid", "Duplicate", "Duplicate"]
    assert result["summary"]["valid_invoices"] == 1
    assert result["summary"]["duplicate_invoices"] == 2
    assert result["summary"]["duplicate_flag_count"] == 2


def test_duplicate_and_invalid_conditions_together():
    df = pd.DataFrame([
        {
            "invoice_number": "INV-3001",
            "vendor_name": "Delta Traders",
            "invoice_date": "2026-10-01",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
            "currency": "USD",
        },
        {
            "invoice_number": "  inv-3001 ",
            "vendor_name": "delta traders",
            "invoice_date": "2026-10-01",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "9999.00",
            "currency": "USD",
        },
    ])

    result = process_invoices(df)
    second = result["records"][1]
    assert second["is_duplicate"] is True
    assert second["status"] == "Invalid"
    assert result["summary"]["total_invoices"] == 2
    assert result["summary"]["valid_invoices"] == 1
    assert result["summary"]["invalid_invoices"] == 1
    assert result["summary"]["duplicate_invoices"] == 0
    assert result["summary"]["duplicate_flag_count"] == 1
    assert (
        result["summary"]["valid_invoices"]
        + result["summary"]["warning_invoices"]
        + result["summary"]["duplicate_invoices"]
        + result["summary"]["invalid_invoices"]
    ) == result["summary"]["total_invoices"]


def test_per_currency_summary_totals():
    df = pd.DataFrame([
        {
            "invoice_number": "INV-4001",
            "vendor_name": "Vendor A",
            "invoice_date": "2026-10-01",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
            "currency": "INR",
        },
        {
            "invoice_number": "INV-4002",
            "vendor_name": "Vendor B",
            "invoice_date": "2026-10-02",
            "subtotal": "200.00",
            "tax_amount": "36.00",
            "total_amount": "236.00",
            "currency": "USD",
        },
    ])

    summary = process_invoices(df)["summary"]
    assert summary["currency_reconciliation"]["INR"]["total_amount"] == 1180.00
    assert summary["currency_reconciliation"]["USD"]["total_amount"] == 236.00
