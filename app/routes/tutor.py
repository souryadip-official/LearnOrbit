"""
LearnOrbit AI Tutor Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import LearningSession, LearningBehavior
from app.services.ai_service import (
    call_ai, build_tutor_system, detect_misconception, infer_learning_style
)
from app.services.mastery_service import recalculate_topic_mastery, topic_slug
from datetime import datetime
import re

tutor_bp = Blueprint("tutor", __name__)


def _get_or_require_key():
    """Return (provider, model, api_key) or None if missing."""
    return current_user.ai_provider, current_user.ai_model, current_user.get_ai_api_key()


@tutor_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_session():
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        topic = data.get("topic", "").strip()
        if not topic:
            return jsonify({"success": False, "error": "Topic required"}), 400

        provider, model, api_key = _get_or_require_key()
        if not api_key:
            if request.is_json:
                return jsonify({"success": False,
                                "error": "Please add your API key in Settings first!",
                                "redirect": url_for("auth.settings")}), 400
            flash("Please add your AI API key in Settings! ⚙️", "warning")
            return redirect(url_for("auth.settings"))

        session_obj = LearningSession(user_id=current_user.id, topic=topic)
        db.session.add(session_obj)
        db.session.commit()

        if request.is_json:
            return jsonify({"success": True, "session_id": session_obj.id,
                            "redirect": url_for("tutor.chat", session_id=session_obj.id)})
        return redirect(url_for("tutor.chat", session_id=session_obj.id))

    return render_template("tutor/new_session.html")


@tutor_bp.route("/<int:session_id>")
@login_required
def chat(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()
    return render_template("tutor/chat.html", session=session_obj)


@tutor_bp.route("/<int:session_id>/message", methods=["POST"])
@login_required
def send_message(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    if session_obj.status != "active":
        return jsonify({"error": "Session is not active."}), 400

    data = request.get_json()
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    provider, model, api_key = _get_or_require_key()

    # Build conversation history for the AI
    conv = session_obj.conversation
    messages_for_ai = [{"role": m["role"], "content": m["content"]} for m in conv[-20:]]
    messages_for_ai.append({"role": "user", "content": user_msg})

    behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    style = behavior.preferred_style if behavior else "balanced"
    system = build_tutor_system(session_obj.topic, session_obj.difficulty_level, style)

    ai_reply = call_ai(provider, model, api_key, messages_for_ai, system=system, max_tokens=2048)

    # Detect [ADAPT: level] tag from AI response
    adapt_match = re.search(r'\[ADAPT:\s*(beginner|intermediate|advanced)\]', ai_reply, re.IGNORECASE)
    if adapt_match:
        session_obj.difficulty_level = adapt_match.group(1).lower()
        ai_reply = re.sub(r'\[ADAPT:\s*\w+\]', '', ai_reply).strip()

    # Save messages
    session_obj.add_message("user", user_msg)
    session_obj.add_message("assistant", ai_reply)
    db.session.commit()

    # Async misconception check (lightweight, non-blocking)
    misconception = None
    if len(user_msg) > 30:  # Only for substantive messages
        try:
            result = detect_misconception(
                provider, model, api_key,
                session_obj.topic, user_msg,
                "Core concept of " + session_obj.topic
            )
            if result.get("has_misconception") and result.get("confidence", 0) > 0.65:
                misconception = result
                miscs = session_obj.misconceptions
                miscs.append({
                    "text": result.get("misconception"),
                    "correction": result.get("correction"),
                })
                session_obj.misconceptions = miscs
                db.session.commit()
        except Exception:
            pass

    return jsonify({
        "reply": ai_reply,
        "misconception": misconception,
        "difficulty": session_obj.difficulty_level,
    })


@tutor_bp.route("/<int:session_id>/end", methods=["POST"])
@login_required
def end_session(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    was_active = session_obj.status == "active"
    session_obj.status = "completed"
    if not session_obj.ended_at:
        session_obj.ended_at = datetime.utcnow()

    # Recompute from persisted session results so a quiz taken after ending the
    # session is reflected when its submission route recalculates mastery.
    mastery = recalculate_topic_mastery(
        current_user.id, topic_slug(session_obj.topic)
    )
    if mastery:
        session_obj.mastery_score = mastery.overall

    # Update behavior
    behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    if behavior and was_active:
        behavior.total_sessions += 1
        behavior.last_active = datetime.utcnow()
        if session_obj.started_at and session_obj.ended_at:
            duration = (session_obj.ended_at - session_obj.started_at).total_seconds() / 60
            n = behavior.total_sessions
            behavior.avg_session_duration_mins = (
                (behavior.avg_session_duration_mins * (n - 1) + duration) / n
            )
        profile = behavior.profile
        topics = profile.get("topics", [])
        if session_obj.topic not in topics:
            topics.append(session_obj.topic)
        profile["topics"] = topics
        behavior.profile = profile
        behavior.total_topics = len(topics)

    db.session.commit()

    return jsonify({
        "success": True,
        "mastery": mastery.to_dict() if mastery else {},
        "redirect": url_for("quiz.quiz_page", session_id=session_id),
    })
