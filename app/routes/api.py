"""
LearnOrbit Internal API Routes
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from app import db
from app.models import TopicMastery, LearningBehavior, LearningSession

api_bp = Blueprint("api", __name__)


@api_bp.route("/providers")
@login_required
def providers():
    return jsonify(current_app.config["AI_PROVIDERS"])


@api_bp.route("/theme", methods=["POST"])
@login_required
def toggle_theme():
    data = request.get_json()
    theme = data.get("theme", "light")
    if theme in ("light", "dark"):
        current_user.theme = theme
        db.session.commit()
    return jsonify({"theme": current_user.theme})


@api_bp.route("/mastery")
@login_required
def mastery():
    records = TopicMastery.query.filter_by(user_id=current_user.id).all()
    return jsonify([r.to_dict() for r in records])


@api_bp.route("/behavior")
@login_required
def behavior():
    b = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    return jsonify(b.to_dict() if b else {})


@api_bp.route("/sessions")
@login_required
def sessions():
    limit = int(request.args.get("limit", 10))
    records = (LearningSession.query
               .filter_by(user_id=current_user.id)
               .order_by(LearningSession.started_at.desc())
               .limit(limit).all())
    return jsonify([r.to_dict() for r in records])


@api_bp.route("/validate-key", methods=["POST"])
@login_required
def validate_key():
    """Quick API key sanity check by making a minimal call."""
    data = request.get_json()
    provider = data.get("provider", current_user.ai_provider)
    model = data.get("model", current_user.ai_model)
    api_key = data.get("api_key", current_user.ai_api_key_enc)

    if not api_key:
        return jsonify({"valid": False, "message": "No API key provided."})

    from app.services.ai_service import call_ai
    result = call_ai(provider, model, api_key,
                     [{"role": "user", "content": "Say only: OK"}],
                     max_tokens=10)
    valid = not result.startswith("❌")
    return jsonify({"valid": valid, "message": result[:100] if not valid else "API key is valid! ✅"})
