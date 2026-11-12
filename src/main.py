"""Flask web application entry point for DIT – Invoice Processing Automation."""

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, Optional
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from src.business_rules import process_invoices
from src.data_reader import DataReaderError, read_invoice_file
from src.logger import get_logger
from src.report_generator import generate_all_reports

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample" / "sample_invoices.csv"
UPLOAD_FOLDER = PROJECT_ROOT / "data" / "input"
MASTER_STORE_PATH = UPLOAD_FOLDER / "master_invoice_register.csv"
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

SAFE_DATA_LOAD_ERROR = (
    "Unable to load the active invoice dataset. Please upload a valid CSV or Excel (.xlsx) file "
    "or reset to the sample dataset."
)
SAFE_UPLOAD_VALIDATION_ERROR = (
    "The uploaded file could not be processed. Please ensure it is a non-empty .csv or .xlsx file "
    "containing the required invoice columns and at least one invoice record."
)
SAFE_UNEXPECTED_ERROR = (
    "An unexpected error occurred while processing the request. Please try again."
)

logger = get_logger(__name__)

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
app.config["SECRET_KEY"] = (
    os.environ.get("FLASK_SECRET_KEY")
    or os.environ.get("SECRET_KEY")
    or "dev-only-dit-invoice-secret-key"
)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

APP_STATE: Dict[str, Any] = {
    "cached_path": None,
    "cached_mtime": None,
    "cached_data": None,
}


def _ensure_master_store() -> Path:
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    if not MASTER_STORE_PATH.exists():
        if SAMPLE_DATA_PATH.exists():
            import shutil
            shutil.copyfile(SAMPLE_DATA_PATH, MASTER_STORE_PATH)
        else:
            import pandas as pd
            pd.DataFrame(columns=[
                "invoice_number", "vendor_name", "invoice_date",
                "subtotal", "tax_amount", "total_amount", "currency"
            ]).to_csv(MASTER_STORE_PATH, index=False)
    return MASTER_STORE_PATH


def _is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _get_processed_data() -> Dict[str, Any]:
    active_path = _ensure_master_store()
    mtime = active_path.stat().st_mtime
    if (
        APP_STATE["cached_data"] is not None
        and APP_STATE["cached_path"] == str(active_path)
        and APP_STATE["cached_mtime"] == mtime
    ):
        return APP_STATE["cached_data"]

    try:
        df = read_invoice_file(active_path)
    except Exception as exc:
        logger.warning("Could not read master store (%s), reinitializing: %s", active_path, exc)
        import pandas as pd
        df = pd.DataFrame(columns=[
            "invoice_number", "vendor_name", "invoice_date",
            "subtotal", "tax_amount", "total_amount", "currency"
        ])

    processed = process_invoices(df)
    report_paths = generate_all_reports(processed)
    processed["report_paths"] = report_paths
    processed["active_filename"] = "Master Invoice Database"

    APP_STATE["cached_path"] = str(active_path)
    APP_STATE["cached_mtime"] = mtime
    APP_STATE["cached_data"] = processed
    return processed


@app.context_processor
def inject_global_data():
    try:
        data = _get_processed_data()
        count = data["summary"].get("total_invoices", 0)
    except Exception:
        count = 0
    return {"global_invoice_count": count}


@app.route("/")
def dashboard():
    try:
        data = _get_processed_data()
        return render_template(
            "index.html",
            summary=data["summary"],
            records=data["records"][:10],
            exceptions=data["exceptions"][:5],
            active_filename=data["active_filename"],
        )
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("Dashboard load error: %s", exc)
        return render_template(
            "index.html",
            summary={},
            records=[],
            exceptions=[],
            active_filename=APP_STATE["active_filename"],
            error=SAFE_DATA_LOAD_ERROR,
        ), 500
    except Exception:
        logger.exception("Unexpected error loading dashboard")
        return render_template(
            "index.html",
            summary={},
            records=[],
            exceptions=[],
            active_filename=APP_STATE["active_filename"],
            error=SAFE_UNEXPECTED_ERROR,
        ), 500


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        if "invoice_file" not in request.files:
            flash("No file part found in the upload request.", "error")
            return redirect(url_for("upload"))

        uploaded = request.files["invoice_file"]
        if not uploaded or uploaded.filename == "":
            flash("Please select a CSV or Excel (.xlsx) file to upload.", "error")
            return redirect(url_for("upload"))

        if not _is_allowed_file(uploaded.filename):
            flash("Invalid file type. Please upload a .csv or .xlsx file.", "error")
            return redirect(url_for("upload"))

        UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        safe_name = secure_filename(uploaded.filename)
        if not safe_name:
            flash("Invalid filename provided.", "error")
            return redirect(url_for("upload"))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = UPLOAD_FOLDER / f"{timestamp}_{safe_name}"

        try:
            uploaded.save(saved_path)
            new_df = read_invoice_file(saved_path)
            master_path = _ensure_master_store()

            try:
                import pandas as pd
                existing_df = read_invoice_file(master_path)
            except Exception:
                import pandas as pd
                existing_df = pd.DataFrame(columns=[
                    "invoice_number", "vendor_name", "invoice_date",
                    "subtotal", "tax_amount", "total_amount", "currency"
                ])

            upload_mode = request.form.get("upload_mode", "append").strip().lower()
            if upload_mode == "replace":
                combined_df = new_df.copy()
            else:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)

            combined_df.to_csv(master_path, index=False)
            APP_STATE["cached_data"] = None
            APP_STATE["cached_mtime"] = None
            _get_processed_data()

            if upload_mode == "replace":
                flash(f"Replaced database with {len(new_df)} invoice(s) from '{safe_name}'.", "success")
            else:
                flash(
                    f"Successfully added {len(new_df)} invoice(s) from '{safe_name}'. Total invoices stored: {len(combined_df)}.",
                    "success",
                )
            logger.info("Updated master invoice dataset with %d rows from %s (mode=%s). Total=%d", len(new_df), safe_name, upload_mode, len(combined_df))
            return redirect(url_for("invoices"))
        except (FileNotFoundError, DataReaderError) as exc:
            saved_path.unlink(missing_ok=True)
            logger.warning("Rejected uploaded file (%s): %s", safe_name, exc)
            flash(SAFE_UPLOAD_VALIDATION_ERROR, "error")
            return redirect(url_for("upload"))
        except Exception:
            saved_path.unlink(missing_ok=True)
            logger.exception("Unexpected error processing uploaded file '%s'", safe_name)
            flash(SAFE_UNEXPECTED_ERROR, "error")
            return redirect(url_for("upload"))

    return render_template("upload.html", active_filename="Master Invoice Database")


@app.route("/invoices")
def invoices():
    try:
        data = _get_processed_data()
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("Invoices route error: %s", exc)
        flash(SAFE_DATA_LOAD_ERROR, "error")
        return render_template("invoices.html", invoices=[], summary={}, search_query="", status_filter="all"), 500
    except Exception:
        logger.exception("Unexpected error loading invoices page")
        flash(SAFE_UNEXPECTED_ERROR, "error")
        return render_template("invoices.html", invoices=[], summary={}, search_query="", status_filter="all"), 500

    search_query = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "all").strip().lower()

    filtered = data["records"]
    if search_query:
        filtered = [
            rec
            for rec in filtered
            if search_query in str(rec.get("invoice_number", "")).lower()
            or search_query in str(rec.get("vendor_name", "")).lower()
            or search_query in str(rec.get("currency", "")).lower()
        ]
    if status_filter != "all":
        filtered = [
            rec for rec in filtered if str(rec.get("status", "")).lower() == status_filter
        ]

    return render_template(
        "invoices.html",
        invoices=filtered,
        summary=data["summary"],
        search_query=request.args.get("q", ""),
        status_filter=status_filter,
        active_filename=data["active_filename"],
    )


@app.route("/invoices/delete/<int:row_number>", methods=["POST"])
def delete_invoice(row_number: int):
    try:
        master_path = _ensure_master_store()
        df = read_invoice_file(master_path)
        row_idx = row_number - 1
        if 0 <= row_idx < len(df):
            inv_num = str(df.iloc[row_idx].get("invoice_number", "")).strip() or f"Row {row_number}"
            df = df.drop(df.index[row_idx]).reset_index(drop=True)
            df.to_csv(master_path, index=False)
            APP_STATE["cached_data"] = None
            APP_STATE["cached_mtime"] = None
            _get_processed_data()
            flash(f"Invoice '{inv_num}' (Row #{row_number}) has been deleted.", "success")
        else:
            flash(f"Invoice at row #{row_number} not found.", "error")
    except Exception as exc:
        logger.exception("Error deleting invoice at row %d: %s", row_number, exc)
        flash("Failed to delete invoice.", "error")

    referrer = request.referrer
    if referrer and any(k in referrer for k in ("invoices", "exceptions", "dashboard")):
        return redirect(referrer)
    return redirect(url_for("invoices"))


@app.route("/invoices/clear-all", methods=["POST"])
def clear_all_invoices():
    try:
        master_path = _ensure_master_store()
        import pandas as pd
        empty_df = pd.DataFrame(columns=[
            "invoice_number", "vendor_name", "invoice_date",
            "subtotal", "tax_amount", "total_amount", "currency"
        ])
        empty_df.to_csv(master_path, index=False)
        APP_STATE["cached_data"] = None
        APP_STATE["cached_mtime"] = None
        _get_processed_data()
        flash("All invoices have been cleared from the database.", "info")
    except Exception as exc:
        logger.exception("Error clearing all invoices: %s", exc)
        flash("Failed to clear invoices.", "error")
    return redirect(url_for("invoices"))


@app.route("/exceptions")
def exceptions():
    try:
        data = _get_processed_data()
        return render_template(
            "exceptions.html",
            exceptions=data["exceptions"],
            summary=data["summary"],
            active_filename=data["active_filename"],
        )
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("Exceptions route error: %s", exc)
        flash(SAFE_DATA_LOAD_ERROR, "error")
        return render_template("exceptions.html", exceptions=[], summary={}), 500
    except Exception:
        logger.exception("Unexpected error loading exceptions page")
        flash(SAFE_UNEXPECTED_ERROR, "error")
        return render_template("exceptions.html", exceptions=[], summary={}), 500


@app.route("/reconciliation")
def reconciliation():
    try:
        data = _get_processed_data()
        return render_template(
            "reconciliation.html",
            summary=data["summary"],
            valid_records=data["valid_records"],
            exceptions=data["exceptions"],
            active_filename=data["active_filename"],
        )
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("Reconciliation route error: %s", exc)
        flash(SAFE_DATA_LOAD_ERROR, "error")
        return render_template("reconciliation.html", summary={}, valid_records=[], exceptions=[]), 500
    except Exception:
        logger.exception("Unexpected error loading reconciliation page")
        flash(SAFE_UNEXPECTED_ERROR, "error")
        return render_template("reconciliation.html", summary={}, valid_records=[], exceptions=[]), 500


@app.route("/reports")
def reports():
    try:
        data = _get_processed_data()
        return render_template(
            "reports.html",
            summary=data["summary"],
            report_paths=data["report_paths"],
            active_filename=data["active_filename"],
        )
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("Reports route error: %s", exc)
        flash(SAFE_DATA_LOAD_ERROR, "error")
        return render_template("reports.html", summary={}, report_paths={}), 500
    except Exception:
        logger.exception("Unexpected error loading reports page")
        flash(SAFE_UNEXPECTED_ERROR, "error")
        return render_template("reports.html", summary={}, report_paths={}), 500


@app.route("/reports/download/<report_type>")
def download_report(report_type: str):
    try:
        data = _get_processed_data()
    except Exception:
        logger.exception("Error preparing report download for type '%s'", report_type)
        abort(500)

    file_format = request.args.get("format", "csv").strip().lower()
    if file_format not in {"csv", "xlsx"}:
        abort(400)

    report_map = data["report_paths"]
    if report_type not in report_map:
        abort(404)

    target_path: Optional[Path] = report_map[report_type].get(file_format)
    if not target_path or not Path(target_path).exists():
        abort(404)

    return send_file(target_path, as_attachment=True, download_name=Path(target_path).name)


@app.route("/api/dashboard-data")
def api_dashboard_data():
    try:
        data = _get_processed_data()
        return jsonify({
            "active_filename": data["active_filename"],
            "summary": data["summary"],
        })
    except (FileNotFoundError, DataReaderError) as exc:
        logger.error("API dashboard error: %s", exc)
        return jsonify({"error": SAFE_DATA_LOAD_ERROR}), 500
    except Exception:
        logger.exception("Unexpected API dashboard error")
        return jsonify({"error": SAFE_UNEXPECTED_ERROR}), 500


@app.route("/reset-sample", methods=["POST"])
def reset_sample():
    try:
        master_path = _ensure_master_store()
        import shutil
        shutil.copyfile(SAMPLE_DATA_PATH, master_path)
        APP_STATE["cached_data"] = None
        APP_STATE["cached_mtime"] = None
        _get_processed_data()
        flash("Reset invoice database to default sample dataset.", "info")
    except Exception as exc:
        logger.exception("Error resetting to sample dataset: %s", exc)
        flash("Failed to reset dataset.", "error")
    return redirect(url_for("dashboard"))


@app.errorhandler(413)
def file_too_large(_error):
    flash("Uploaded file exceeds the 16 MB limit.", "error")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    logger.info("Starting DIT – Invoice Processing Automation server (host=%s, port=%d, debug=%s)...", host, port, debug_mode)
    app.run(debug=debug_mode, host=host, port=port)
