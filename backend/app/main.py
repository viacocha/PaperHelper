from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from app.services.compare import compare_reviews
from app.services.report_generator import generate_report
from app.services.reviewer import EssayReviewer
from app.services.standards import load_standard_library

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

library = load_standard_library()
reviewer = EssayReviewer(library)
generated_reports: dict[str, Path] = {}


@app.after_request
def apply_cors(response):  # type: ignore[no-untyped-def]
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "PaperHelper API"})


@app.route("/api/standards", methods=["GET"])
def standards():
    return jsonify({
        "subject": library.subject,
        "version": library.version,
        "pass_score": library.pass_score,
        "standards": [
            {"id": item.id, "name": item.name, "category": item.category}
            for item in library.all()
        ],
    })


@app.route("/api/review", methods=["POST", "OPTIONS"])
def review_essay():
    if request.method == "OPTIONS":
        return ("", 204)

    file = request.files.get("file")
    standard_id = request.form.get("standard_id")
    if not file or not file.filename or not file.filename.lower().endswith(".docx"):
        return jsonify({"detail": "仅支持上传 .docx 文件。"}), 400

    upload_path, original_name = _save_upload(file)

    review = reviewer.review(
        upload_path,
        preferred_standard_id=standard_id or None,
        original_filename=original_name,
    )
    report_path = REPORT_DIR / review.suggested_report_name
    generate_report(review, report_path)
    generated_reports[review.suggested_report_name] = report_path
    return jsonify(review.to_dict())


@app.route("/api/compare", methods=["POST", "OPTIONS"])
def compare_essays():
    if request.method == "OPTIONS":
        return ("", 204)

    original_file = request.files.get("original_file")
    revised_file = request.files.get("revised_file")
    standard_id = request.form.get("standard_id")

    if not original_file or not original_file.filename or not original_file.filename.lower().endswith(".docx"):
        return jsonify({"detail": "请上传修改前 .docx 文件。"}), 400
    if not revised_file or not revised_file.filename or not revised_file.filename.lower().endswith(".docx"):
        return jsonify({"detail": "请上传修改后 .docx 文件。"}), 400

    original_path, original_name = _save_upload(original_file)
    revised_path, revised_name = _save_upload(revised_file)

    original_review = reviewer.review(
        original_path,
        preferred_standard_id=standard_id or None,
        original_filename=original_name,
    )
    revised_review = reviewer.review(
        revised_path,
        preferred_standard_id=standard_id or None,
        original_filename=revised_name,
    )
    return jsonify(compare_reviews(original_review, revised_review).to_dict())


@app.route("/api/reports/<report_name>", methods=["GET"])
def download_report(report_name: str):
    report_path = generated_reports.get(report_name)
    if not report_path or not report_path.exists():
        return jsonify({"detail": "建议报告不存在。"}), 404

    return send_file(
        report_path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=report_name,
    )


def _save_upload(file):
    original_name = Path(file.filename).name
    safe_basename = secure_filename(original_name) or f"{uuid4().hex}.docx"
    safe_name = f"{uuid4().hex}_{safe_basename}"
    upload_path = UPLOAD_DIR / safe_name
    file.save(upload_path)
    return upload_path, original_name


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)
