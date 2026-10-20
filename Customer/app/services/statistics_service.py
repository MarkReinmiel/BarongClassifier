from __future__ import annotations

from app.models import Classification, CustomerUser


def dashboard_stats(user: CustomerUser) -> dict:
    total = Classification.query.filter_by(user_id=user.id).count()
    recent = (
        Classification.query.filter_by(user_id=user.id)
        .order_by(Classification.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "textile_types": 3,
        "model_accuracy": "84%",
        "images_classified": total,
        "recent": [
            {
                "label": row.predicted_label,
                "confidence": row.confidence,
                "image_name": row.image_name,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
            for row in recent
        ],
    }
