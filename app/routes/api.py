"""
LearnOrbit Internal API Routes
"""

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from app import db
from app.models import TopicMastery, LearningBehavior, LearningSession
import requests

api_bp = Blueprint("api", __name__)


@api_bp.route("/providers")
@login_required
def providers():
    return jsonify(current_app.config["AI_PROVIDERS"])


@api_bp.route("/provider-key-status/<provider>")
@login_required
def provider_key_status(provider):
    if provider not in current_app.config["AI_PROVIDERS"]:
        return jsonify({"error": "Unknown AI provider."}), 404
    return jsonify({"has_key": bool(current_user.get_ai_api_key(provider))})


@api_bp.route("/huggingface-models")
@login_required
def huggingface_models():
    """Return chat models currently served by at least one HF provider."""
    fallback = current_app.config["AI_PROVIDERS"]["huggingface"]["models"]
    try:
        response = requests.get("https://router.huggingface.co/v1/models", timeout=15)
        response.raise_for_status()
        models = response.json().get("data", [])
        model_ids = sorted({
            item["id"] for item in models
            if item.get("id")
            and any(provider.get("status") == "live" for provider in item.get("providers", []))
            and "text" in item.get("architecture", {}).get("output_modalities", [])
        }, key=str.casefold)
        if model_ids:
            return jsonify({"models": model_ids})
    except (requests.RequestException, ValueError, TypeError):
        pass
    return jsonify({"models": fallback})


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
    api_key = data.get("api_key") or current_user.get_ai_api_key(provider)

    if not api_key:
        return jsonify({"valid": False, "message": "No API key provided."})

    from app.services.ai_service import call_ai
    result = call_ai(provider, model, api_key,
                     [{"role": "user", "content": "Say only: OK"}],
                     max_tokens=10)
    valid = not result.startswith(("❌", "⏳"))
    provider_name = current_app.config["AI_PROVIDERS"].get(provider, {}).get("name", provider)
    # Distinguish rejected credentials from network, model, and provider failures.
    if result.startswith("❌ Invalid API key"):
        message = f"{provider_name} rejected this API key. Check that it is a valid key for {provider_name}."
        return jsonify({"valid": False, "message": message, "error_type": "authentication"})
    if result.startswith("❌ API key was rejected or lacks permission"):
        return jsonify({"valid": False, "message": result[2:], "error_type": "permission"})
    if result.startswith("❌ Unexpected error:"):
        message = "Could not connect to the AI provider. Check your internet connection and try again."
        return jsonify({"valid": False, "message": message, "error_type": "connection"})
    if result.startswith("❌ API error"):
        message = result[:300]
        return jsonify({"valid": False, "message": message, "error_type": "provider"})
    if result.startswith("⏳"):
        return jsonify({"valid": False, "message": result, "error_type": "rate_limit"})
    return jsonify({"valid": valid, "message": "API key is valid! ✅" if valid else result[:300]})
