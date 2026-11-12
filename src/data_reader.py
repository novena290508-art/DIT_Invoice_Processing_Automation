"""Data ingestion module for CSV and Excel (.xlsx) invoice files."""

import codecs
from collections import Counter
import csv
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)

CANONICAL_COLUMNS = [
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
]

HEADER_ALIASES: Dict[str, str] = {
    "invoice_number": "invoice_number",
    "invoice number": "invoice_number",
    "invoicenumber": "invoice_number",
    "invoice_no": "invoice_number",
    "vendor_name": "vendor_name",
    "vendor name": "vendor_name",
    "vendorname": "vendor_name",
    "supplier_name": "vendor_name",
    "invoice_date": "invoice_date",
    "invoice date": "invoice_date",
    "invoicedate": "invoice_date",
    "date": "invoice_date",
    "subtotal": "subtotal",
    "sub_total": "subtotal",
    "sub total": "subtotal",
    "tax_amount": "tax_amount",
    "tax amount": "tax_amount",
    "taxamount": "tax_amount",
    "tax": "tax_amount",
    "total_amount": "total_amount",
    "total amount": "total_amount",
    "totalamount": "total_amount",
    "total": "total_amount",
    "currency": "currency",
    "curr": "currency",
}

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


class DataReaderError(Exception):
    """Raised when an invoice file cannot be read or fails structural checks."""


def normalize_headers(columns: List[str]) -> List[str]:
    """Trim whitespace, handle case differences, and map recognized headers."""
    normalized: List[str] = []
    for col in columns:
        cleaned = " ".join(str(col).strip().split()).lower()
        underscored = cleaned.replace(" ", "_")
        mapped = HEADER_ALIASES.get(cleaned) or HEADER_ALIASES.get(underscored) or underscored
        normalized.append(mapped)
    return normalized


def find_duplicate_headers(columns: List[str]) -> List[str]:
    """Return header names that appear more than once."""
    counts = Counter(columns)
    return [col for col, count in counts.items() if count > 1]


def validate_raw_headers(raw_headers: List[str], filename: str) -> List[str]:
    """Check raw headers for exact and normalized duplicates before Pandas renaming."""
    if not raw_headers:
        logger.error("Invoice file %s is completely empty.", filename)
        raise DataReaderError(f"The uploaded file '{filename}' is empty.")

    trimmed_raw = [str(col).strip() for col in raw_headers]
    exact_dups = find_duplicate_headers(trimmed_raw)
    if exact_dups:
        logger.error("Exact duplicate headers in %s: %s", filename, exact_dups)
        raise DataReaderError(
            f"Duplicate column header(s) detected: {', '.join(exact_dups)}. "
            "Each column must have a unique name."
        )

    normalized_cols = normalize_headers(trimmed_raw)
    normalized_dups = find_duplicate_headers(normalized_cols)
    if normalized_dups:
        logger.error("Duplicate normalized headers in %s: %s", filename, normalized_dups)
        raise DataReaderError(
            f"Duplicate normalized column header(s) detected: {', '.join(normalized_dups)}. "
            "Each column must map to a unique field."
        )

    return normalized_cols


def _read_raw_csv_headers(path: Path) -> Tuple[List[str], str]:
    """Detect a consistent CSV encoding and return (raw_headers, encoding)."""
    raw_bytes = path.read_bytes()
    encodings = (
        ("utf-8-sig", "latin-1")
        if raw_bytes.startswith(codecs.BOM_UTF8)
        else ("utf-8", "latin-1")
    )

    selected_encoding = "latin-1"
    for enc in encodings:
        try:
            raw_bytes.decode(enc)
            selected_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    with path.open("r", encoding=selected_encoding, newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, []), selected_encoding


def validate_columns(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Verify that all canonical columns exist in the DataFrame."""
    missing = [col for col in CANONICAL_COLUMNS if col not in df.columns]
    return len(missing) == 0, missing


def read_invoice_file(file_path: Path | str) -> pd.DataFrame:
    """Read a CSV or Excel (.xlsx) invoice file while preserving all raw rows."""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        logger.error("Invoice file not found: %s", path.name)
        raise FileNotFoundError(f"Invoice file not found: {path.name}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        logger.error("Unsupported file extension '%s' for file %s", ext, path.name)
        raise DataReaderError(
            f"Unsupported file format '{ext}'. Allowed formats: .csv, .xlsx"
        )

    try:
        if ext == ".csv":
            raw_headers, csv_encoding = _read_raw_csv_headers(path)
            normalized_cols = validate_raw_headers(raw_headers, path.name)
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=csv_encoding)
        else:
            header_df = pd.read_excel(
                path, header=None, nrows=1, dtype=str, keep_default_na=False, engine="openpyxl"
            )
            raw_headers = header_df.iloc[0].tolist() if not header_df.empty else []
            normalized_cols = validate_raw_headers(raw_headers, path.name)
            df = pd.read_excel(path, dtype=str, keep_default_na=False, engine="openpyxl")
    except DataReaderError:
        raise
    except Exception as exc:
        logger.error("Failed to read invoice file %s: %s", path.name, exc)
        raise DataReaderError(f"Unable to read file '{path.name}': {exc}") from exc

    if len(df.columns) == 0:
        logger.error("Invoice file %s is completely empty.", path.name)
        raise DataReaderError(f"The uploaded file '{path.name}' is empty.")

    df.columns = normalized_cols

    is_valid, missing_cols = validate_columns(df)
    if not is_valid:
        logger.error("Missing canonical columns in %s: %s", path.name, missing_cols)
        raise DataReaderError(
            f"Missing required columns: {', '.join(missing_cols)}. "
            f"Expected: {', '.join(CANONICAL_COLUMNS)}"
        )

    if df.empty:
        logger.warning("Invoice file %s contains headers but no invoice records.", path.name)
        raise DataReaderError(
            f"The file '{path.name}' contains headers but no invoice records."
        )

    raw_df = df[CANONICAL_COLUMNS].copy()
    logger.info("Loaded %d invoice row(s) from %s", len(raw_df), path.name)
    return raw_df
