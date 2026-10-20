from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.services.classification_service import ClassificationError, classify_upload
from app.utils.security import current_user, login_required, no_store

bp = Blueprint("classify", __name__)


@bp.get("/classify")
@login_required
def classify_page():
    response = render_template("classify.html", user=current_user(), active="classify")
    return no_store(response)


@bp.post("/classify")
@login_required
def classify_submit():
    user = current_user()
    upload = request.files.get("file") or request.files.get("textileImage")
    if not upload or not getattr(upload, "filename", None):
        flash("Please select or capture a textile image first.", "error")
        return redirect(url_for("classify.classify_page"))

    try:
        result = classify_upload(user, upload)
    except ClassificationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("classify.classify_page"))

    response = render_template(
        "result.html",
        user=user,
        result=result,
        active="classify",
    )
    return no_store(response)
