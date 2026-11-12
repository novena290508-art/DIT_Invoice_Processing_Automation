"""Unit tests for src/report_generator.py."""

import pandas as pd

from src.business_rules import process_invoices
from src.report_generator import (
    generate_exception_report,
    generate_invoice_register,
    generate_reconciliation_summary,
)


def test_generate_invoice_register_csv_and_excel(tmp_path):
    df = pd.DataFrame([
        {
            "invoice_number": "INV-5001",
            "vendor_name": "Alpha Corp",
            "invoice_date": "2026-10-01",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
            "currency": "INR",
        }
    ])
    processed = process_invoices(df)
    outputs = generate_invoice_register(processed["records"], output_dir=tmp_path, include_excel=True)

    assert outputs["csv"].exists()
    assert outputs["xlsx"].exists()

    csv_df = pd.read_csv(outputs["csv"])
    xlsx_df = pd.read_excel(outputs["xlsx"], engine="openpyxl")
    assert len(csv_df) == 1
    assert len(xlsx_df) == 1
    assert csv_df.loc[0, "status"] == "Valid"


def test_generate_exception_report_csv_and_excel(tmp_path):
    df = pd.DataFrame([
        {
            "invoice_number": "INV-5002",
            "vendor_name": "Beta Corp",
            "invoice_date": "2026-13-45",
            "subtotal": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
            "currency": "INR",
        },
        {
            "invoice_number": "INV-5003",
            "vendor_name": "Gamma Corp",
            "invoice_date": "2026-10-05",
            "subtotal": "0",
            "tax_amount": "0",
            "total_amount": "0",
            "currency": "INR",
        },
    ])
    processed = process_invoices(df)
    outputs = generate_exception_report(processed["exceptions"], output_dir=tmp_path, include_excel=True)

    assert outputs["csv"].exists()
    assert outputs["xlsx"].exists()

    exc_df = pd.read_csv(outputs["csv"])
    assert len(exc_df) == 2
    assert set(exc_df["status"]) == {"Invalid", "Warning"}


def test_generate_reconciliation_summary_per_currency(tmp_path):
    df = pd.DataFrame([
        {
            "invoice_number": "INV-6001",
            "vendor_name": "India Vendor",
            "invoice_date": "2026-10-01",
            "subtotal": "10000.00",
            "tax_amount": "1800.00",
            "total_amount": "11800.00",
            "currency": "INR",
        },
        {
            "invoice_number": "INV-6002",
            "vendor_name": "US Vendor",
            "invoice_date": "2026-10-02",
            "subtotal": "500.00",
            "tax_amount": "90.00",
            "total_amount": "590.00",
            "currency": "USD",
        },
    ])
    processed = process_invoices(df)
    outputs = generate_reconciliation_summary(processed["summary"], output_dir=tmp_path, include_excel=True)

    assert outputs["csv"].exists()
    assert outputs["xlsx"].exists()

    summary_df = pd.read_csv(outputs["csv"])
    inr_row = summary_df[(summary_df["currency"] == "INR") & (summary_df["metric"] == "Valid Total Amount")]
    usd_row = summary_df[(summary_df["currency"] == "USD") & (summary_df["metric"] == "Valid Total Amount")]
    assert float(inr_row["value"].iloc[0]) == 11800.00
    assert float(usd_row["value"].iloc[0]) == 590.00


def test_empty_dataset_report_generation(tmp_path):
    reg_out = generate_invoice_register([], output_dir=tmp_path, include_excel=True)
    exc_out = generate_exception_report([], output_dir=tmp_path, include_excel=True)
    rec_out = generate_reconciliation_summary({}, output_dir=tmp_path, include_excel=True)

    assert reg_out["csv"].exists() and reg_out["xlsx"].exists()
    assert exc_out["csv"].exists() and exc_out["xlsx"].exists()
    assert rec_out["csv"].exists() and rec_out["xlsx"].exists()
    assert pd.read_csv(reg_out["csv"]).empty
    assert pd.read_csv(exc_out["csv"]).empty
