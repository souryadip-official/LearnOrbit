"""
LearnOrbit AI Tutor Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import LearningSession, TopicMastery, LearningBehavior
from app.services.ai_service import (
    call_ai, build_tutor_system, detect_misconception, infer_learning_style
)
from datetime import datetime
import re

tutor_bp = Blueprint("tutor", __name__)


def _get_or_require_key():
    """Return (provider, model, api_key) or None if missing."""
    return current_user.ai_provider, current_user.ai_model, current_user.ai_api_key_enc


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

    session_obj.status = "completed"
    session_obj.ended_at = datetime.utcnow()

    # Update topic mastery
    topic_slug = session_obj.topic.lower().replace(" ", "-")[:100]
    mastery = TopicMastery.query.filter_by(
        user_id=current_user.id, topic_slug=topic_slug).first()
    if not mastery:
        mastery = TopicMastery(
            user_id=current_user.id, topic=session_obj.topic, topic_slug=topic_slug)
        db.session.add(mastery)

    # Score from quiz + engagement heuristic
    quiz_score = session_obj.quiz_score or 0
    msg_engagement = min(session_obj.messages_count / 20.0, 1.0) * 30

    mastery.understanding = min(100, mastery.understanding + quiz_score * 0.4 + msg_engagement)
    mastery.application = min(100, mastery.application + quiz_score * 0.3)
    mastery.problem_solving = min(100, mastery.problem_solving + quiz_score * 0.2)
    mastery.retention = min(100, mastery.retention + quiz_score * 0.1)
    mastery.sessions_count += 1
    mastery.last_studied = datetime.utcnow()
    mastery.recalculate_overall()
    session_obj.mastery_score = mastery.overall

    # Update behavior
    behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    if behavior:
        behavior.total_sessions += 1
        behavior.last_active = datetime.utcnow()
        if session_obj.started_at and session_obj.ended_at:
            duration = (session_obj.ended_at - session_obj.started_at).seconds / 60
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
        "mastery": mastery.to_dict(),
        "redirect": url_for("quiz.quiz_page", session_id=session_id),
    })
