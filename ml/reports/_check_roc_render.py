from app import create_app
from flask import render_template

app = create_app()
with app.app_context():
    from app.services.model_analytics_service import analytics_json, metrics_candidates, _registry_production_paths

    art, keras, row = _registry_production_paths()
    print("prod_art", art)
    print("prod_label", (row or {}).get("version_label"))
    for path in metrics_candidates():
        print("cand", path, "exists", path.is_file())
    data = analytics_json()
    p = data["performance"]
    print("source", data["overview"].get("metrics_source"))
    print("ovr", p.get("roc_auc_ovr_macro"), "ovo", p.get("roc_auc_ovo_macro"))
    print("note", p.get("roc_auc_note"))

with app.test_request_context("/model-analytics"):
    html = render_template(
        "model_analytics.html",
        user={"id": 1, "email": "a@b.c", "name": "t", "role": "owner"},
        analytics=data,
        active="analytics",
        app_name="Owner",
    )
a = html.find("ma-metric-grid ma-metric-grid--3")
print(html[a : a + 700])
