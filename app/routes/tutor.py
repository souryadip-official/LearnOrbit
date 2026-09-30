"""
LearnOrbit AI Tutor Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import LearningSession, LearningBehavior
from app.models import SessionDocument, QuizAttempt, QuizGeneration
from app.models import SessionRecallSchedule, TopicReviewSchedule
from app.services.ai_service import (
    call_ai, build_tutor_system, detect_misconception, infer_learning_style,
    supports_temperature, _is_provider_error, _parse_json_payload,
)
from app.services.mastery_service import (
    recalculate_all_topic_mastery,
    recalculate_topic_mastery,
    topic_slug,
)
from datetime import datetime, timedelta
import re
import json

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
            flash("Please add your AI API key in Settings.", "warning")
            return redirect(url_for("auth.settings"))

        daily_limit = current_app.config["PRICING"].get(current_user.plan, {}).get("sessions_per_day", -1)
        if daily_limit >= 0:
            today = datetime.utcnow().date()
            started_today = LearningSession.query.filter(
                LearningSession.user_id == current_user.id,
                LearningSession.started_at >= datetime.combine(today, datetime.min.time()),
            ).count()
            if started_today >= daily_limit:
                message = "You have reached today's session limit on Explorer. Upgrade for unlimited tutor sessions."
                if request.is_json:
                    return jsonify({"success": False, "error": message,
                                    "redirect": url_for("features.pricing")}), 403
                flash(message, "warning")
                return redirect(url_for("features.pricing"))

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
    reteach_prompt = None
    if request.args.get("review") == "latest" and session_obj.status == "reviewing":
        attempt = QuizAttempt.query.filter_by(session_id=session_obj.id).order_by(
            QuizAttempt.attempted_at.desc()).first()
        if attempt and attempt.score is not None and attempt.score < 40:
            missed = [question for question in attempt.questions if not question.get("is_correct")]
            details = "\n".join(
                f"- {question.get('question', 'Concept check')}\n"
                f"  Student answer: {question.get('options', {}).get(question.get('user_answer'), '(no answer)')}\n"
                f"  Correct answer: {question.get('options', {}).get(question.get('correct'), '')}\n"
                f"  Concept tested: {question.get('misconception_check') or 'Explain the underlying idea.'}"
                for question in missed
            )
            reteach_prompt = (
                f"I just scored {attempt.score:.0f}% on the quiz for {session_obj.topic}. "
                "Please review the questions I missed below. Explain the underlying ideas "
                "step by step, with an example where useful, then pause so I can ask follow-up questions. "
                "Do not end the session.\n\n" + details
            )
    return render_template("tutor/chat.html", session=session_obj,
                           temperature_supported=supports_temperature(current_user.ai_provider, current_user.ai_model),
                           reteach_prompt=reteach_prompt)


@tutor_bp.route("/<int:session_id>/message", methods=["POST"])
@login_required
def send_message(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    if session_obj.status not in {"active", "reviewing"}:
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
    from app.models import UserProfile
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    style = (profile.teaching_style if profile and profile.teaching_style else behavior.preferred_style if behavior else "balanced")
    system = build_tutor_system(session_obj.topic, session_obj.difficulty_level, style)
    # Ground answers in this session's BYOB notes using semantic/keyword RRF.
    documents = SessionDocument.query.filter_by(session_id=session_obj.id, user_id=current_user.id).all()
    if documents:
        from app.routes.features import hybrid_retrieve, _embeddings
        passages = []
        query_vector = _embeddings([f"{session_obj.topic}\n{user_msg}"])
        for document in documents:
            cached_vectors = None
            if document.embedding_provider == provider and document.embeddings_json:
                try: cached_vectors = json.loads(document.embeddings_json)
                except (TypeError, ValueError): cached_vectors = None
            for hit in hybrid_retrieve(document.extracted_text, f"{session_obj.topic}\n{user_msg}", 3, cached_vectors=cached_vectors, query_vector=query_vector):
                passages.append(f"[From {document.filename}] {hit['text'][:1500]}")
        if passages:
            system += "\n\nSTUDENT-PROVIDED SOURCE NOTES (use as grounding, cite the filename in your answer; tell the student when notes do not support a claim):\n" + "\n\n".join(passages[:4])

    try:
        temperature = max(0.0, min(2.0, float(data.get("temperature", 0.7))))
    except (TypeError, ValueError):
        temperature = 0.7
    ai_reply = call_ai(provider, model, api_key, messages_for_ai, system=system,
                       temperature=temperature if supports_temperature(provider, model) else None)

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
                session_obj.topic, user_msg, ai_reply,
            )
            if result.get("has_misconception") and result.get("confidence", 0) > 0.65:
                misconception = result
                miscs = session_obj.misconceptions
                miscs.append({
                    "text": result.get("misconception"),
                    "correction": result.get("correction"),
                    "confidence": result.get("confidence"),
                    "topic": session_obj.topic,
                    "detected_at": datetime.utcnow().isoformat(),
                })
                session_obj.misconceptions = miscs[-100:]
                db.session.commit()
        except (RuntimeError, ValueError) as error:
            current_app.logger.warning(
                "Misconception analysis skipped for session %s: %s",
                session_obj.id, error,
            )

    return jsonify({
        "reply": ai_reply,
        "misconception": misconception,
        "difficulty": session_obj.difficulty_level,
    })


def _tool_session(session_id, flag):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    if not current_app.config["PRICING"].get(current_user.plan, {}).get(flag, False):
        return session_obj, (jsonify({
            "error": "This learning mode is available on Scholar and Academy.",
            "upgrade_url": url_for("features.pricing"),
        }), 403)
    api_key = current_user.get_ai_api_key()
    if not api_key:
        return session_obj, (jsonify({"error": "Add your AI provider key in Settings first."}), 400)
    return (session_obj, current_user.ai_provider, current_user.ai_model, api_key), None


@tutor_bp.route("/<int:session_id>/tools/debate", methods=["POST"])
@login_required
def debate(session_id):
    resolved, error = _tool_session(session_id, "debate_mode")
    if error:
        return error
    session_obj, provider, model, api_key = resolved
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Debate input could not be read."}), 400
    claim = data.get("claim", "")
    if not isinstance(claim, str) or not claim.strip() or len(claim) > 800:
        return jsonify({"error": "Enter a focused claim or question of up to 800 characters."}), 400
    history = data.get("history", [])
    if not isinstance(history, list) or len(history) > 16:
        return jsonify({"error": "Debate history is invalid. Start a new debate and try again."}), 400
    safe_history = []
    for turn in history:
        if (not isinstance(turn, dict)
                or turn.get("agent") not in {"advocate", "skeptic"}
                or not isinstance(turn.get("content"), str)):
            return jsonify({"error": "Debate history contains an invalid turn."}), 400
        safe_history.append({
            "agent": turn["agent"],
            "content": turn["content"][:2200],
        })
    try:
        round_number = max(1, min(100, int(data.get("round", 1))))
    except (TypeError, ValueError):
        return jsonify({"error": "Debate round is invalid."}), 400

    transcript = "\n\n".join(
        f"Agent {'A · Advocate' if turn['agent'] == 'advocate' else 'B · Skeptic'}: "
        f"{turn['content']}"
        for turn in safe_history[-12:]
    )
    context = (
        f"Topic: {session_obj.topic}\nClaim: {claim.strip()}\n"
        f"Debate round: {round_number}\n"
        f"Previous debate turns:\n{transcript or '(This is the opening round.)'}"
    )
    advocate = call_ai(
        provider, model, api_key,
        [{"role": "user", "content": context}],
        system=(
            "You are Agent A, the Advocate in a rigorous educational debate. "
            "Make one concise, evidence-based argument supporting the claim. In later "
            "rounds, directly answer Agent B's latest objection and add a new angle. "
            "Distinguish established facts from assumptions. Do not claim sources you "
            "cannot verify. Keep this turn under 180 words."
        ),
        max_tokens=500,
    )
    if _is_provider_error(advocate):
        current_app.logger.warning(
            "Advocate failed in debate for session %s: %s",
            session_id, advocate[:200],
        )
        return jsonify({"error": advocate[:500]}), 502
    skeptic = call_ai(
        provider, model, api_key,
        [{
            "role": "user",
            "content": (
                f"{context}\n\nAgent A's new argument:\n{advocate[:2500]}"
            ),
        }],
        system=(
            "You are Agent B, the Skeptic in a rigorous educational debate. "
            "Challenge Agent A's newest argument with a fair counterargument, identify "
            "assumptions or missing evidence, and add a new perspective. Do not repeat "
            "old objections or merely disagree. Keep this turn under 180 words."
        ),
        max_tokens=500,
    )
    if _is_provider_error(skeptic):
        current_app.logger.warning(
            "Skeptic failed in debate for session %s: %s",
            session_id, skeptic[:200],
        )
        return jsonify({"error": skeptic[:500]}), 502
    return jsonify({
        "round": round_number,
        "turns": [
            {"agent": "advocate", "content": advocate},
            {"agent": "skeptic", "content": skeptic},
        ],
    })


@tutor_bp.route("/<int:session_id>/tools/teach-back", methods=["POST"])
@login_required
def teach_back(session_id):
    resolved, error = _tool_session(session_id, "teach_back_mode")
    if error:
        return error
    session_obj, provider, model, api_key = resolved
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Teach-back input could not be read."}), 400
    action = data.get("action")
    if action == "prompt":
        messages = [{"role": "user", "content": f"Create one short, specific prompt that asks a student to teach a key idea from {session_obj.topic} to a curious classmate. Do not give the answer."}]
        system = "You are a curious learner preparing a teach-back exercise. Return only the single prompt."
    elif action == "feedback":
        answer = data.get("answer", "")
        if not isinstance(answer, str) or len(answer.strip()) < 20 or len(answer) > 2500:
            return jsonify({"error": "Write at least 20 characters and no more than 2,500 characters."}), 400
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 500:
            return jsonify({"error": "Generate a teach-back prompt before submitting an explanation."}), 400
        try:
            iteration = max(1, min(100, int(data.get("iteration", 1))))
        except (TypeError, ValueError):
            return jsonify({"error": "Teach-back iteration is invalid."}), 400
        history = data.get("history", [])
        if not isinstance(history, list) or len(history) > 16:
            return jsonify({"error": "Teach-back history is invalid. Start a new exercise and try again."}), 400
        transcript = []
        for turn in history:
            if (not isinstance(turn, dict)
                    or turn.get("role") not in {"student", "twin"}
                    or not isinstance(turn.get("content"), str)):
                return jsonify({"error": "Teach-back history contains an invalid turn."}), 400
            transcript.append(
                f"{'Student' if turn['role'] == 'student' else 'Twin student'}: "
                f"{turn['content'][:1800]}"
            )
        messages = [{
            "role": "user",
            "content": (
                f"Topic: {session_obj.topic}\nExercise: {prompt.strip()}\n"
                f"Iteration: {iteration}\nPrevious turns:\n"
                f"{chr(10).join(transcript[-12:]) or '(First explanation.)'}\n\n"
                f"Student explanation:\n{answer.strip()}"
            ),
        }]
        system = (
            "You are a curious twin student who is trying to genuinely understand the "
            "learner's explanation. Evaluate whether it is accurate, coherent, and covers "
            "the important idea; do not demand exact wording. Return strict JSON with "
            "keys clear (boolean), feedback (string), and question (string). If anything "
            "is unclear or incorrect, set clear=false and ask one focused follow-up "
            "question that checks the missing piece. A first attempt can never finish "
            "the exercise: even if it seems excellent, set clear=false and ask a brief "
            "transfer question to verify understanding. Only set clear=true from "
            "iteration 2 onward when the explanation and follow-up are genuinely clear. "
            "Never disclose a hidden answer before the student gets a chance to respond."
        )
    else:
        return jsonify({"error": "Choose a teach-back action."}), 400
    reply = call_ai(provider, model, api_key, messages, system=system, max_tokens=800)
    if _is_provider_error(reply):
        current_app.logger.warning(
            "Teach-back provider failed for learning session %s: %s",
            session_id, reply[:200],
        )
        return jsonify({"error": reply[:500]}), 502
    if action == "prompt":
        return jsonify({"reply": reply})
    evaluation = _parse_json_payload(reply)
    if (
        not isinstance(evaluation, dict)
        or not isinstance(evaluation.get("clear"), bool)
        or not isinstance(evaluation.get("feedback"), str)
        or not isinstance(evaluation.get("question"), str)
    ):
        current_app.logger.warning(
            "Teach-back returned invalid structured feedback for session %s",
            session_id,
        )
        return jsonify({
            "error": "The twin student returned an invalid evaluation. Please submit the explanation again."
        }), 502
    is_clear = evaluation["clear"] and iteration >= 2
    question = evaluation["question"].strip()[:700]
    if not is_clear and not question:
        return jsonify({
            "error": "The twin student could not form a follow-up question. Please try again."
        }), 502
    return jsonify({
        "feedback": evaluation["feedback"].strip()[:1600],
        "question": question,
        "clear": is_clear,
        "iteration": iteration,
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
    recall_schedule = SessionRecallSchedule.query.filter_by(
        user_id=current_user.id, session_id=session_obj.id
    ).first()
    if recall_schedule is None:
        baseline = float(session_obj.quiz_score if session_obj.quiz_score is not None else 100)
        ended_at = session_obj.ended_at
        recall_schedule = SessionRecallSchedule(
            user_id=current_user.id,
            session_id=session_obj.id,
            cycle_number=1,
            interval_days=10,
            baseline_score=baseline,
            last_score=baseline,
            last_test_at=ended_at,
            next_test_at=ended_at + timedelta(days=10),
            history=[{
                "cycle": 0,
                "elapsed_days": 0,
                "score": baseline,
                "relative_recall": 100,
                "tested_at": ended_at.isoformat(),
                "is_baseline_estimate": session_obj.quiz_score is None,
            }],
        )
        db.session.add(recall_schedule)

    # Uploaded notes and their cached embedding vectors belong to this session.
    # Remove the file and index records when the learning session is finished.
    for document in SessionDocument.query.filter_by(session_id=session_obj.id, user_id=current_user.id).all():
        try:
            import os
            if document.storage_path and os.path.isfile(document.storage_path):
                os.remove(document.storage_path)
        except OSError:
            pass
        db.session.delete(document)

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


@tutor_bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id):
    session_obj = LearningSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    documents = SessionDocument.query.filter_by(
        session_id=session_obj.id, user_id=current_user.id
    ).all()
    for document in documents:
        try:
            import os
            if document.storage_path and os.path.isfile(document.storage_path):
                os.remove(document.storage_path)
        except OSError:
            current_app.logger.exception(
                "Could not remove uploaded document while deleting learning session %s",
                session_obj.id,
            )
            return jsonify({"error": "Could not remove every uploaded file. The session was not deleted; please retry."}), 500
    for document in documents:
        db.session.delete(document)
    QuizGeneration.query.filter_by(
        session_id=session_obj.id, user_id=current_user.id
    ).delete(synchronize_session=False)
    SessionRecallSchedule.query.filter_by(
        session_id=session_obj.id, user_id=current_user.id
    ).delete(synchronize_session=False)
    db.session.delete(session_obj)
    db.session.commit()
    # Remove orphan mastery rows as well as refreshing topics with other
    # remaining sessions, so deleted learning leaves no visible traces.
    recalculate_all_topic_mastery(current_user.id)
    behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    if behavior:
        remaining_topics = {
            row.topic for row in LearningSession.query.filter_by(user_id=current_user.id).all()
        }
        profile = behavior.profile
        profile["topics"] = [topic for topic in profile.get("topics", []) if topic in remaining_topics]
        behavior.profile = profile
        behavior.total_topics = len(profile["topics"])
    remaining_slugs = {
        topic_slug(row.topic) for row in
        LearningSession.query.filter_by(user_id=current_user.id).all()
    }
    for schedule in TopicReviewSchedule.query.filter_by(user_id=current_user.id).all():
        if schedule.topic_slug not in remaining_slugs:
            db.session.delete(schedule)
    db.session.commit()
    return jsonify({"success": True})
