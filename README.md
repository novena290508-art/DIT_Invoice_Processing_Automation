# DIT – Invoice Processing Automation

[![CI Test Suite](https://github.com/novena290508-art/DIT_Invoice_Processing_Automation/actions/workflows/ci.yml/badge.svg)](https://github.com/novena290508-art/DIT_Invoice_Processing_Automation/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask 3.0](https://img.shields.io/badge/framework-Flask_3.0-green.svg)](https://flask.palletsprojects.com/)
[![Tests Passing](https://img.shields.io/badge/pytest-17%20passed-brightgreen.svg)](https://github.com/novena290508-art/DIT_Invoice_Processing_Automation)

## 1. Project Title & Team Details
- **Project Title:** DIT – Invoice Processing Automation
- **Organization:** DefineInfoTech Pvt. Ltd. (DIT)
- **Team Members & DIT Internship IDs:**
  - Nisha M (`DIT2026S1008`) — Team Lead & Scrum Master
  - Barani Kumar P (`DIT2026S1005`) — System Architect
  - Novena L (`DIT2026S1006`) — Extraction Specialist
  - Kayalvizhi S (`DIT2026S1007`) — Validation Rules Lead
  - Harini R N (`DIT2026S1009`) — Reconciliation Engineer
  - R. Sangamithra (`DIT2026S1010`) — Frontend & QA Lead

## 2. Business Problem & Objectives
Manual invoice verification across spreadsheets is slow and error-prone. This application automates CSV and Excel (`.xlsx`) invoice ingestion, field/date/numeric validation, `subtotal + tax_amount = total_amount` verification, normalized duplicate detection, exception classification, and per-currency reconciliation through an enterprise Flask web dashboard.

## 3. Features & Scope
- Executive Finance Dashboard with live KPI cards and Chart.js visualizations
- Safe `.csv` and `.xlsx` upload handling (original input files preserved)
- Searchable and filterable Invoice Register
- Automated validation (required fields, dates, numeric/non-negative amounts, `0.01` total tolerance)
- Zero-value (`0, 0, 0`) classification as `Warning / Review Required`
- Normalized duplicate detection (`vendor_name + invoice_number`, case/whitespace-insensitive)
- Per-currency reconciliation (`INR`, `USD`, `EUR` calculated separately)
- Downloadable CSV and Excel reports

## 4. Python Version & Dependencies
- **Python:** Python 3.10+
- **Dependencies:** `Flask`, `pandas`, `openpyxl`, `pytest`, `python-dotenv`, `Werkzeug` (see `requirements.txt`)

## 5. Installation & Configuration
```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```
Optional environment variables: `FLASK_SECRET_KEY` (defaults to local dev key) and `FLASK_DEBUG=true` (disabled by default).

## 6. Input Format & Data Dictionary
| Column | Type | Required | Description |
|---|---|---|---|
| `invoice_number` | String | Yes | Unique invoice identifier per vendor |
| `vendor_name` | String | Yes | Vendor or supplier name |
| `invoice_date` | Date (`YYYY-MM-DD`) | Yes | Invoice issue date |
| `subtotal` | Numeric (`>= 0`) | Yes | Pre-tax invoice amount |
| `tax_amount` | Numeric (`>= 0`) | Yes | Tax amount |
| `total_amount` | Numeric (`>= 0`) | Yes | Must equal `subtotal + tax_amount` (±0.01) |
| `currency` | String | No | Currency code (e.g., `INR`, `USD`, `EUR`) |

## 7. Instructions to Run the Application
Run from the project root directory:
```bash
python -m src.main
```
Open `http://127.0.0.1:5000` in your browser.

## 8. Instructions to Run Tests
```bash
pytest -q
```

## 9. Output File Locations
- `data/output/invoice_register.csv` & `.xlsx` — Full processed invoice register
- `reports/exception_report.csv` & `.xlsx` — Invalid, duplicate, and warning records
- `reports/reconciliation_summary.csv` & `.xlsx` — Status counts and per-currency totals

## 10. Validation Rules & Business Assumptions
- Primary statuses are mutually exclusive (`Invalid > Duplicate > Warning > Valid`) and sum to `total_invoices`.
- All-zero invoices (`0, 0, 0`) are flagged as `Warning / Review Required`.
- Currencies are reconciled separately and never summed across different currencies.

## 11. Screenshots & Demonstration Reference
Save UI and test execution screenshots inside `screenshots/` for final DIT internship review.

## 12. Known Limitations & Future Improvements
- Supports structured `.csv` and `.xlsx` files (no OCR for scanned PDFs).
- Uses single-user in-memory `APP_STATE` intended for local internship demonstration.
