"""
LearnOrbit Quiz Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import LearningSession, QuizAttempt
from app.services.ai_service import generate_quiz

quiz_bp = Blueprint("quiz", __name__)


@quiz_bp.route("/<int:session_id>")
@login_required
def quiz_page(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()
    return render_template("quiz/quiz.html", session=session_obj)


@quiz_bp.route("/<int:session_id>/generate", methods=["POST"])
@login_required
def generate(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    provider = current_user.ai_provider
    model = current_user.ai_model
    api_key = current_user.ai_api_key_enc

    if not api_key:
        return jsonify({"error": "API key missing"}), 400

    # Extract key areas from conversation
    conv = session_obj.conversation
    key_text = " ".join(m["content"] for m in conv[-10:] if m["role"] == "assistant")[:500]

    result = generate_quiz(provider, model, api_key, session_obj.topic, key_text)

    if "error" in result:
        return jsonify({"error": result["error"]}), 500

    return jsonify({"questions": result.get("questions", [])})


@quiz_bp.route("/<int:session_id>/submit", methods=["POST"])
@login_required
def submit(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    data = request.get_json()
    answers = data.get("answers", {})  # {question_id: chosen_option}
    questions = data.get("questions", [])

    correct = 0
    evaluated = []
    for q in questions:
        qid = str(q["id"])
        user_ans = answers.get(qid, "")
        is_correct = user_ans == q["correct"]
        if is_correct:
            correct += 1
        evaluated.append({
            **q,
            "user_answer": user_ans,
            "is_correct": is_correct,
        })

    total = len(questions)
    score = round((correct / total) * 100, 1) if total > 0 else 0

    # Save attempt
    attempt = QuizAttempt(
        session_id=session_id,
        score=score,
        total_questions=total,
        correct_answers=correct,
    )
    attempt.questions = evaluated
    db.session.add(attempt)

    # Update session quiz score (best score)
    if session_obj.quiz_score is None or score > session_obj.quiz_score:
        session_obj.quiz_score = score
    db.session.commit()

    return jsonify({
        "score": score,
        "correct": correct,
        "total": total,
        "evaluated": evaluated,
        "attempt_id": attempt.id,
    })
