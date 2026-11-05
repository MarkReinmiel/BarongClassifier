from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from app.services.classification_service import ClassificationError, classify_image
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("classifier", __name__)


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/classify", methods=["GET"])
@nickname_required
def classify_page():
    from app.services.history_service import list_for_user
    from app.services.statistics_service import _format_recent_when

    user = current_user()
    result = list_for_user(user, page=1, per_page=4)
    recent = []
    for row in result.get("items") or []:
        label = row.display_name or row.predicted_label or ""
        key = (row.predicted_label or row.display_name or "").strip().lower()
        key = key.replace("ñ", "n").replace("piña", "pina")
        image_path = (row.image_path or row.image_reference or "") or ""
        recent.append(
            {
                "label": label,
                "confidence": float(row.confidence or row.confidence_score or 0),
                "image_name": row.image_name or row.file_name or "image",
                "image_path": image_path,
                "textile_key": key,
                "created_label": _format_recent_when(row.created_at),
            }
        )
    return render_template(
        "classifier.html",
        user=user,
        recent=recent,
    )


@bp.route("/classify", methods=["POST"])
@nickname_required
def classify_submit():
    user = current_user()
    file = request.files.get("file") or request.files.get("camera_file") or request.files.get("image")
    wants_json = (
        request.accept_mimetypes.best == "application/json"
        or request.is_json
        or bool(request.headers.get("X-Requested-With"))
    )
    if not file or not file.filename:
        if wants_json:
            return jsonify({"error": "Choose an image to classify."}), 400
        flash("Choose an image to classify.", "error")
        return redirect(url_for("classifier.classify_page"))
    try:
        result = classify_image(user, file)
    except (ValueError, ClassificationError) as error:
        status = getattr(error, "status_code", 400)
        if wants_json:
            return jsonify({"error": str(error)}), status
        flash(str(error), "error")
        return redirect(url_for("classifier.classify_page"))
    except Exception:
        current_app.logger.exception("Unexpected classify failure")
        message = "Classification failed on the server. Please try again in a moment."
        if wants_json:
            return jsonify({"error": message}), 500
        flash(message, "error")
        return redirect(url_for("classifier.classify_page"))
    if wants_json:
        return jsonify(result)
    return render_template("result.html", user=user, result=result)


@bp.route("/result")
@nickname_required
def result_page():
    return redirect(url_for("classifier.classify_page"))
