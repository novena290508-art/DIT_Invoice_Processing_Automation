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

# NOTE: Global APP_STATE is intended strictly for a single-user local demonstration
# and is not designed for simultaneous multi-user production sessions.
APP_STATE: Dict[str, Any] = {
    "active_file": SAMPLE_DATA_PATH,
    "active_filename": SAMPLE_DATA_PATH.name,
    "cached_path": None,
    "cached_mtime": None,
    "cached_data": None,
}


def _is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def _get_processed_data() -> Dict[str, Any]:
    active_path = Path(APP_STATE["active_file"])
    if not active_path.exists():
        active_path = SAMPLE_DATA_PATH
        APP_STATE["active_file"] = SAMPLE_DATA_PATH
        APP_STATE["active_filename"] = SAMPLE_DATA_PATH.name

    mtime = active_path.stat().st_mtime
    if (
        APP_STATE["cached_data"] is not None
        and APP_STATE["cached_path"] == str(active_path)
        and APP_STATE["cached_mtime"] == mtime
    ):
        return APP_STATE["cached_data"]

    df = read_invoice_file(active_path)
    processed = process_invoices(df)
    report_paths = generate_all_reports(processed)
    processed["report_paths"] = report_paths
    processed["active_filename"] = APP_STATE["active_filename"]

    APP_STATE["cached_path"] = str(active_path)
    APP_STATE["cached_mtime"] = mtime
    APP_STATE["cached_data"] = processed
    return processed


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
            df = read_invoice_file(saved_path)
            processed = process_invoices(df)
            report_paths = generate_all_reports(processed)
            processed["report_paths"] = report_paths
            processed["active_filename"] = safe_name
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

        APP_STATE["active_file"] = saved_path
        APP_STATE["active_filename"] = safe_name
        APP_STATE["cached_path"] = str(saved_path)
        APP_STATE["cached_mtime"] = saved_path.stat().st_mtime
        APP_STATE["cached_data"] = processed

        logger.info("Activated uploaded invoice dataset: %s", saved_path.name)
        flash(f"Successfully uploaded and processed '{safe_name}'.", "success")
        return redirect(url_for("dashboard"))

    return render_template("upload.html", active_filename=APP_STATE["active_filename"])


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
    APP_STATE["active_file"] = SAMPLE_DATA_PATH
    APP_STATE["active_filename"] = SAMPLE_DATA_PATH.name
    APP_STATE["cached_path"] = None
    APP_STATE["cached_mtime"] = None
    APP_STATE["cached_data"] = None
    flash("Reset active dataset to sample_invoices.csv.", "info")
    return redirect(url_for("dashboard"))


@app.errorhandler(413)
def file_too_large(_error):
    flash("Uploaded file exceeds the 16 MB limit.", "error")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
    logger.info("Starting DIT – Invoice Processing Automation server (debug=%s)...", debug_mode)
    app.run(debug=debug_mode, host="127.0.0.1", port=5000)
