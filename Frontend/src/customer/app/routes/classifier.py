from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.services.classification_service import ClassificationError, classify_image
from app.utils.security import current_user, nickname_required, no_store

bp = Blueprint("classifier", __name__)


@bp.after_request
def _private_headers(response):
    return no_store(response)


@bp.route("/classify", methods=["GET"])
@nickname_required
def classify_page():
    return render_template("classifier.html", user=current_user())


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
    if wants_json:
        return jsonify(result)
    return render_template("result.html", user=user, result=result)


@bp.route("/result")
@nickname_required
def result_page():
    return redirect(url_for("classifier.classify_page"))
