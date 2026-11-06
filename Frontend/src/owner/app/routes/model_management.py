"""Owner Model Management: train / evaluate / deploy / rollback."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request

from app.services.model_registry_service import (
    ModelRegistryError,
    dashboard_payload,
    deploy_candidate,
    evaluate_candidate,
    read_training_log,
    reject_candidate,
    restore_version,
    rollback_production,
    start_training,
)
from app.utils.security import current_user, login_required, no_store

bp = Blueprint("model_management", __name__)


@bp.get("/model-management")
@login_required
def model_management_page():
    user = current_user()
    error = ""
    payload = {
        "production": None,
        "candidate": None,
        "active_job": None,
        "versions": [],
        "deployments": [],
        "dataset": {},
        "production_metrics": {},
        "candidate_metrics": {},
        "classifications_handled": 0,
        "min_test_accuracy": 0.85,
        "can_start_training": False,
        "can_retry": False,
        "can_evaluate": False,
        "can_deploy": False,
        "can_rollback": False,
    }
    try:
        payload = dashboard_payload()
    except ModelRegistryError as exc:
        error = str(exc)
    except Exception as exc:
        current_app.logger.exception("model_management_page failed")
        error = f"Model registry unavailable: {exc}"

    response = render_template(
        "model_management.html",
        user=user,
        active="model_management",
        data=payload,
        error=error,
    )
    return no_store(response)


@bp.get("/api/model-management/status")
@login_required
def model_status_api():
    try:
        return jsonify({"ok": True, **dashboard_payload()})
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.get("/api/model-management/logs")
@login_required
def model_logs_api():
    version_id = (request.args.get("version_id") or "").strip() or None
    return jsonify({"ok": True, "log": read_training_log(version_id)})


@bp.post("/api/model-management/train")
@login_required
def model_train_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    retry = bool(payload.get("retry"))
    new_major = bool(payload.get("new_major"))
    try:
        # Default: next revision under the current major (v2.2, v2.3, …).
        # new_major=True only when Owner explicitly starts a new major generation.
        result = start_training(actor, retry=retry, new_major=new_major)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/model-management/evaluate")
@login_required
def model_evaluate_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    version_id = (payload.get("version_id") or "").strip() or None
    try:
        result = evaluate_candidate(actor, version_id)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/model-management/deploy")
@login_required
def model_deploy_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    version_id = (payload.get("version_id") or "").strip()
    if not version_id:
        return jsonify({"ok": False, "error": "version_id is required."}), 400
    try:
        result = deploy_candidate(actor, version_id)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/model-management/reject")
@login_required
def model_reject_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    version_id = (payload.get("version_id") or "").strip()
    if not version_id:
        return jsonify({"ok": False, "error": "version_id is required."}), 400
    try:
        result = reject_candidate(actor, version_id)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/model-management/rollback")
@login_required
def model_rollback_api():
    actor = current_user()
    assert actor is not None
    try:
        result = rollback_production(actor)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code


@bp.post("/api/model-management/restore")
@login_required
def model_restore_api():
    actor = current_user()
    assert actor is not None
    payload = request.get_json(silent=True) or {}
    version_id = (payload.get("version_id") or "").strip()
    if not version_id:
        return jsonify({"ok": False, "error": "version_id is required."}), 400
    try:
        result = restore_version(actor, version_id)
        return jsonify(result)
    except ModelRegistryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), exc.status_code
