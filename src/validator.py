"""Validation engine for invoice fields, dates, numeric amounts, and parity."""

from datetime import datetime
import math
from typing import Any, Dict, List, Optional
import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS = ("invoice_number", "vendor_name")
AMOUNT_FIELDS = ("subtotal", "tax_amount", "total_amount")
TOTAL_TOLERANCE = 0.01
ZERO_VALUE_WARNING = "WARNING / REVIEW REQUIRED: Zero-value invoice (subtotal=0, tax_amount=0, total_amount=0)"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def parse_valid_date(value: Any) -> Optional[str]:
    if _is_missing(value):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_numeric_amount(value: Any) -> Optional[float]:
    if _is_missing(value):
        return None
    text = str(value).strip().replace(",", "")
    try:
        num = float(text)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def validate_invoice_row(row: Dict[str, Any], row_index: int) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    invoice_number = "" if _is_missing(row.get("invoice_number")) else str(row.get("invoice_number")).strip()
    vendor_name = "" if _is_missing(row.get("vendor_name")) else str(row.get("vendor_name")).strip()
    currency = "" if _is_missing(row.get("currency")) else str(row.get("currency")).strip().upper()

    if not invoice_number:
        errors.append("Missing required field: invoice_number")
    if not vendor_name:
        errors.append("Missing required field: vendor_name")

    parsed_date = parse_valid_date(row.get("invoice_date"))
    if parsed_date is None:
        raw_date = "" if _is_missing(row.get("invoice_date")) else str(row.get("invoice_date")).strip()
        errors.append(f"Invalid invoice_date: '{raw_date or 'EMPTY'}'")

    parsed_amounts: Dict[str, Optional[float]] = {}
    for field in AMOUNT_FIELDS:
        num_val = parse_numeric_amount(row.get(field))
        parsed_amounts[field] = num_val
        if num_val is None:
            raw_val = "" if _is_missing(row.get(field)) else str(row.get(field)).strip()
            errors.append(f"Non-numeric {field}: '{raw_val or 'EMPTY'}'")
        elif num_val < 0:
            errors.append(f"Negative {field} is not allowed: {num_val:.2f}")

    subtotal = parsed_amounts["subtotal"]
    tax_amount = parsed_amounts["tax_amount"]
    total_amount = parsed_amounts["total_amount"]

    if subtotal is not None and tax_amount is not None and total_amount is not None:
        expected_total = round(subtotal + tax_amount, 2)
        if round(abs((subtotal + tax_amount) - total_amount), 4) > TOTAL_TOLERANCE:
            errors.append(
                f"Total mismatch: subtotal ({subtotal:.2f}) + tax_amount ({tax_amount:.2f}) "
                f"= {expected_total:.2f}, but total_amount is {total_amount:.2f}"
            )
        elif subtotal == 0 and tax_amount == 0 and total_amount == 0:
            warnings.append(ZERO_VALUE_WARNING)

    is_valid = len(errors) == 0
    has_warning = len(warnings) > 0
    if not is_valid:
        validation_status = "INVALID"
    elif has_warning:
        validation_status = "WARNING / REVIEW REQUIRED"
    else:
        validation_status = "VALID"

    return {
        "row_number": row_index,
        "invoice_number": str(row.get("invoice_number", "")),
        "vendor_name": str(row.get("vendor_name", "")),
        "invoice_date": str(row.get("invoice_date", "")),
        "parsed_date": parsed_date,
        "subtotal": row.get("subtotal", ""),
        "tax_amount": row.get("tax_amount", ""),
        "total_amount": row.get("total_amount", ""),
        "subtotal_num": subtotal,
        "tax_amount_num": tax_amount,
        "total_amount_num": total_amount,
        "currency": currency or "UNKNOWN",
        "is_valid": is_valid,
        "has_warning": has_warning,
        "validation_status": validation_status,
        "errors": errors,
        "warnings": warnings,
    }


def validate_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    records = df.to_dict(orient="records")
    for idx, record in enumerate(records, start=1):
        results.append(validate_invoice_row(record, row_index=idx))

    invalid_count = sum(1 for item in results if not item["is_valid"])
    warning_count = sum(1 for item in results if item["is_valid"] and item["has_warning"])
    logger.info(
        "Validated %d invoice(s): %d valid, %d warning, %d invalid.",
        len(results),
        len(results) - invalid_count - warning_count,
        warning_count,
        invalid_count,
    )
    return results
