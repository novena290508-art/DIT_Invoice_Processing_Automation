"""Business rules engine for duplicate detection, classification, and currency reconciliation."""

from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from src.logger import get_logger
from src.validator import validate_dataframe

logger = get_logger(__name__)


def normalize_identifier(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).casefold()


def build_duplicate_key(vendor_name: Any, invoice_number: Any) -> Optional[Tuple[str, str]]:
    norm_vendor = normalize_identifier(vendor_name)
    norm_invoice = normalize_identifier(invoice_number)
    if not norm_vendor or not norm_invoice:
        return None
    return (norm_vendor, norm_invoice)


def classify_exception_type(errors: List[str], warnings: List[str], is_duplicate: bool) -> str:
    if is_duplicate and not errors:
        return "Duplicate Invoice"
    if not errors and warnings:
        return "Warning / Review Required"
    joined = " | ".join(errors).lower()
    if "missing required field" in joined:
        return "Missing Required Field"
    if "invalid invoice_date" in joined:
        return "Invalid Date"
    if "non-numeric" in joined:
        return "Non-Numeric Amount"
    if "negative" in joined:
        return "Negative Amount"
    if "total mismatch" in joined:
        return "Total Mismatch"
    if is_duplicate:
        return "Duplicate & Validation Error"
    return "Validation Error"


def process_invoices(df: pd.DataFrame) -> Dict[str, Any]:
    validation_results = validate_dataframe(df)
    seen_keys: Set[Tuple[str, str]] = set()

    processed_records: List[Dict[str, Any]] = []
    valid_records: List[Dict[str, Any]] = []
    warning_records: List[Dict[str, Any]] = []
    exceptions: List[Dict[str, Any]] = []

    valid_count = 0
    warning_count = 0
    duplicate_status_count = 0
    invalid_count = 0
    duplicate_flag_count = 0

    currency_reconciliation: Dict[str, Dict[str, Any]] = {}
    exception_currency_totals: Dict[str, Dict[str, Any]] = {}
    exception_breakdown: Dict[str, int] = {}

    def _init_currency_bucket(bucket: Dict[str, Dict[str, Any]], curr: str) -> Dict[str, Any]:
        if curr not in bucket:
            bucket[curr] = {
                "currency": curr,
                "count": 0,
                "subtotal": 0.0,
                "tax_amount": 0.0,
                "total_amount": 0.0,
            }
        return bucket[curr]

    for item in validation_results:
        dup_key = build_duplicate_key(item["vendor_name"], item["invoice_number"])
        is_duplicate = False
        base_errors = list(item["errors"])
        errors = list(base_errors)
        warnings = list(item["warnings"])

        if dup_key is not None:
            if dup_key in seen_keys:
                is_duplicate = True
                duplicate_flag_count += 1
                errors.append(
                    "Duplicate invoice: normalized vendor_name + invoice_number already exists"
                )
            else:
                seen_keys.add(dup_key)

        if base_errors:
            status = "Invalid"
            invalid_count += 1
        elif is_duplicate:
            status = "Duplicate"
            duplicate_status_count += 1
        elif warnings:
            status = "Warning"
            warning_count += 1
        else:
            status = "Valid"
            valid_count += 1

        all_notes = errors + warnings
        reason_text = "; ".join(all_notes) if all_notes else "Passed all checks"
        curr = item["currency"]

        record = {
            **item,
            "normalized_vendor": normalize_identifier(item["vendor_name"]),
            "normalized_invoice_number": normalize_identifier(item["invoice_number"]),
            "is_duplicate": is_duplicate,
            "status": status,
            "warnings": warnings,
            "errors": errors,
            "reason": reason_text,
        }
        processed_records.append(record)

        if status == "Valid":
            valid_records.append(record)
            bucket = _init_currency_bucket(currency_reconciliation, curr)
            bucket["count"] += 1
            bucket["subtotal"] = round(bucket["subtotal"] + (item["subtotal_num"] or 0.0), 2)
            bucket["tax_amount"] = round(bucket["tax_amount"] + (item["tax_amount_num"] or 0.0), 2)
            bucket["total_amount"] = round(bucket["total_amount"] + (item["total_amount_num"] or 0.0), 2)
        else:
            if status == "Warning":
                warning_records.append(record)

            exc_bucket = _init_currency_bucket(exception_currency_totals, curr)
            exc_bucket["count"] += 1
            if item["subtotal_num"] is not None:
                exc_bucket["subtotal"] = round(exc_bucket["subtotal"] + item["subtotal_num"], 2)
            if item["tax_amount_num"] is not None:
                exc_bucket["tax_amount"] = round(exc_bucket["tax_amount"] + item["tax_amount_num"], 2)
            if item["total_amount_num"] is not None:
                exc_bucket["total_amount"] = round(exc_bucket["total_amount"] + item["total_amount_num"], 2)

            exc_category = classify_exception_type(base_errors, warnings, is_duplicate)
            exception_breakdown[exc_category] = exception_breakdown.get(exc_category, 0) + 1
            exceptions.append({
                "row_number": item["row_number"],
                "invoice_number": item["invoice_number"] or "(Missing)",
                "vendor_name": item["vendor_name"] or "(Missing)",
                "invoice_date": item["invoice_date"] or "(Missing)",
                "subtotal": item["subtotal"],
                "tax_amount": item["tax_amount"],
                "total_amount": item["total_amount"],
                "currency": curr,
                "status": status,
                "category": exc_category,
                "is_duplicate": is_duplicate,
                "reason": reason_text,
            })

    total_invoices = len(processed_records)
    exception_count = len(exceptions)
    pass_rate = round((valid_count / total_invoices) * 100, 2) if total_invoices > 0 else 0.0
    unique_vendors = set(
        record["normalized_vendor"]
        for record in processed_records
        if record.get("normalized_vendor")
    )
    unique_vendor_count = len(unique_vendors)

    summary = {
        "total_invoices": total_invoices,
        "unique_vendor_count": unique_vendor_count,
        "valid_invoices": valid_count,
        "warning_invoices": warning_count,
        "duplicate_invoices": duplicate_status_count,
        "invalid_invoices": invalid_count,
        "duplicate_flag_count": duplicate_flag_count,
        "exception_count": exception_count,
        "pass_rate": pass_rate,
        "currency_reconciliation": currency_reconciliation,
        "exception_currency_totals": exception_currency_totals,
        "exception_breakdown": exception_breakdown,
    }

    logger.info(
        "Reconciliation complete: total=%d, valid=%d, warning=%d, duplicate=%d, invalid=%d (duplicate_flags=%d)",
        total_invoices,
        valid_count,
        warning_count,
        duplicate_status_count,
        invalid_count,
        duplicate_flag_count,
    )

    return {
        "records": processed_records,
        "valid_records": valid_records,
        "warning_records": warning_records,
        "exceptions": exceptions,
        "summary": summary,
    }
