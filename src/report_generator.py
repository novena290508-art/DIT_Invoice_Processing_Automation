"""Report generation module for invoice register, exceptions, and per-currency reconciliation."""

from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
REPORTS_DIR = PROJECT_ROOT / "reports"

REGISTER_COLUMNS = [
    "row_number",
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
    "is_duplicate",
    "status",
    "reason",
]

EXCEPTION_COLUMNS = [
    "row_number",
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
    "status",
    "category",
    "is_duplicate",
    "reason",
]


def _ensure_dirs() -> None:
    DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_invoice_register(
    records: List[Dict[str, Any]],
    output_dir: Path | None = None,
    include_excel: bool = True,
) -> Dict[str, Path]:
    _ensure_dirs()
    target_dir = Path(output_dir) if output_dir else DATA_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=REGISTER_COLUMNS)
    else:
        df = df[[col for col in REGISTER_COLUMNS if col in df.columns]]

    csv_path = target_dir / "invoice_register.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    outputs: Dict[str, Path] = {"csv": csv_path}

    if include_excel:
        xlsx_path = target_dir / "invoice_register.xlsx"
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        outputs["xlsx"] = xlsx_path

    logger.info("Generated invoice register (%d rows) at %s", len(df), csv_path.name)
    return outputs


def generate_exception_report(
    exceptions: List[Dict[str, Any]],
    output_dir: Path | None = None,
    include_excel: bool = True,
) -> Dict[str, Path]:
    _ensure_dirs()
    target_dir = Path(output_dir) if output_dir else REPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(exceptions)
    if df.empty:
        df = pd.DataFrame(columns=EXCEPTION_COLUMNS)
    else:
        df = df[[col for col in EXCEPTION_COLUMNS if col in df.columns]]

    csv_path = target_dir / "exception_report.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    outputs: Dict[str, Path] = {"csv": csv_path}

    if include_excel:
        xlsx_path = target_dir / "exception_report.xlsx"
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        outputs["xlsx"] = xlsx_path

    logger.info("Generated exception report (%d rows) at %s", len(df), csv_path.name)
    return outputs


def generate_reconciliation_summary(
    summary: Dict[str, Any],
    output_dir: Path | None = None,
    include_excel: bool = True,
) -> Dict[str, Path]:
    _ensure_dirs()
    target_dir = Path(output_dir) if output_dir else REPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = [
        {"section": "Counts", "currency": "ALL", "metric": "Total Invoices Processed", "value": summary.get("total_invoices", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Valid Invoices", "value": summary.get("valid_invoices", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Warning / Review Required Invoices", "value": summary.get("warning_invoices", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Duplicate Invoices", "value": summary.get("duplicate_invoices", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Invalid Invoices", "value": summary.get("invalid_invoices", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Total Exception & Review Records", "value": summary.get("exception_count", 0)},
        {"section": "Counts", "currency": "ALL", "metric": "Validation Pass Rate (%)", "value": summary.get("pass_rate", 0.0)},
    ]

    for curr, totals in sorted(summary.get("currency_reconciliation", {}).items()):
        rows.extend([
            {"section": "Valid Totals", "currency": curr, "metric": "Valid Invoice Count", "value": totals.get("count", 0)},
            {"section": "Valid Totals", "currency": curr, "metric": "Valid Subtotal", "value": totals.get("subtotal", 0.0)},
            {"section": "Valid Totals", "currency": curr, "metric": "Valid Tax Amount", "value": totals.get("tax_amount", 0.0)},
            {"section": "Valid Totals", "currency": curr, "metric": "Valid Total Amount", "value": totals.get("total_amount", 0.0)},
        ])

    for curr, totals in sorted(summary.get("exception_currency_totals", {}).items()):
        rows.extend([
            {"section": "Exception/Review Totals", "currency": curr, "metric": "Exception/Review Count", "value": totals.get("count", 0)},
            {"section": "Exception/Review Totals", "currency": curr, "metric": "Exception/Review Total Amount (Numeric Rows)", "value": totals.get("total_amount", 0.0)},
        ])

    df = pd.DataFrame(rows)
    csv_path = target_dir / "reconciliation_summary.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    outputs: Dict[str, Path] = {"csv": csv_path}

    if include_excel:
        xlsx_path = target_dir / "reconciliation_summary.xlsx"
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        outputs["xlsx"] = xlsx_path

    logger.info("Generated reconciliation summary at %s", csv_path.name)
    return outputs


def generate_all_reports(processed_data: Dict[str, Any]) -> Dict[str, Dict[str, Path]]:
    return {
        "invoice_register": generate_invoice_register(processed_data.get("records", [])),
        "exception_report": generate_exception_report(processed_data.get("exceptions", [])),
        "reconciliation_summary": generate_reconciliation_summary(processed_data.get("summary", {})),
    }
