"""
LearnOrbit Quiz Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db
from app.models import (
    LearningSession,
    QuizAttempt,
    QuizGeneration,
    SessionRecallSchedule,
    SessionDocument,
    TopicReviewSchedule,
)
from app.services.ai_service import evaluate_written_answers, generate_quiz
from app.services.mastery_service import recalculate_topic_mastery, topic_slug
from datetime import datetime, timedelta
import secrets
import math

quiz_bp = Blueprint("quiz", __name__)


def _quiz_limit_reached(session_obj):
    limit = current_app.config["PRICING"].get(current_user.plan, {}).get("quizzes_per_session", -1)
    if limit < 0:
        return False
    return QuizAttempt.query.filter_by(session_id=session_obj.id).count() >= limit


def _due_recall_schedule(session_obj):
    return SessionRecallSchedule.query.filter(
        SessionRecallSchedule.user_id == current_user.id,
        SessionRecallSchedule.session_id == session_obj.id,
        SessionRecallSchedule.next_test_at <= datetime.utcnow(),
    ).first()


@quiz_bp.route("/<int:session_id>")
@login_required
def quiz_page(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()
    due_recall = _due_recall_schedule(session_obj)
    if _quiz_limit_reached(session_obj) and not due_recall:
        return render_template("features/upgrade_required.html", feature="Unlimited quiz attempts"), 403
    return render_template("quiz/quiz.html", session=session_obj, due_recall=due_recall)


@quiz_bp.route("/<int:session_id>/generate", methods=["POST"])
@login_required
def generate(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()
    mode = (request.args.get("mode") or "quiz").lower()
    if mode not in {"quiz", "exam"}:
        return jsonify({"error": "Choose Quiz or Exam mode."}), 400
    due_schedule = _due_recall_schedule(session_obj)
    if _quiz_limit_reached(session_obj) and not (mode == "quiz" and due_schedule):
        return jsonify({"error": "Explorer includes one quiz attempt per session. Upgrade to Scholar for unlimited quiz attempts.",
                        "redirect": url_for("features.pricing")}), 403

    provider = current_user.ai_provider
    model = current_user.ai_model
    api_key = current_user.get_ai_api_key()

    if not api_key:
        return jsonify({"error": "No API key is saved for your selected AI provider. Add one in Settings and retry."}), 400

    # Extract key areas from conversation
    conv = session_obj.conversation
    key_text = " ".join(m["content"] for m in conv[-10:] if m["role"] == "assistant")[:500]
    documents = SessionDocument.query.filter_by(session_id=session_obj.id, user_id=current_user.id).all()
    if documents:
        import json
        from app.routes.features import hybrid_retrieve, _embeddings
        query = f"{session_obj.topic} key concepts and learning objectives"
        qvec = _embeddings([query])
        for doc in documents:
            try: cached = json.loads(doc.embeddings_json) if doc.embedding_provider == provider and doc.embeddings_json else None
            except ValueError: cached = None
            hits = hybrid_retrieve(doc.extracted_text, query, 2, cached_vectors=cached, query_vector=qvec)
            key_text += "\nSOURCE NOTES (" + doc.filename + "): " + " ".join(hit["text"][:500] for hit in hits)
        key_text = key_text[:3000]

    # Bring forward concepts missed on earlier attempts so a retry can reinforce them.
    prior_attempt = (QuizAttempt.query.filter_by(session_id=session_obj.id)
                     .order_by(QuizAttempt.attempted_at.desc()).first())
    if prior_attempt:
        weak_items = [item for item in prior_attempt.questions if not item.get("is_correct")]
        if weak_items:
            key_text += "\nPRIOR WEAK CONCEPTS (prioritize these while still covering the session):\n"
            weak_context = []
            for item in weak_items:
                options = item.get("options") if isinstance(item.get("options"), dict) else {}
                answer = item.get("user_answer")
                if isinstance(answer, list):
                    student_answer = ", ".join(str(options.get(key, key)) for key in answer)
                elif isinstance(answer, str):
                    student_answer = options.get(answer, answer) if options else answer
                else:
                    student_answer = "(no answer)"
                correct_answer = item.get("correct")
                if isinstance(correct_answer, list):
                    expected = ", ".join(str(options.get(key, key)) for key in correct_answer)
                elif isinstance(correct_answer, str):
                    expected = options.get(correct_answer, correct_answer)
                else:
                    expected = item.get("reference_answer", "")
                weak_context.append(
                    f"- {item.get('misconception_check') or item.get('question', '')}: "
                    f"student answered {student_answer or '(no answer)'}; expected {expected}"
                )
            key_text += "\n".join(weak_context)
    if mode == "exam" and not current_app.config["PRICING"].get(current_user.plan, {}).get("exam_mode", False):
        return jsonify({"error": "Timed exams with negative marking are available on Scholar and Academy.",
                        "redirect": url_for("features.pricing")}), 403
    result = generate_quiz(provider, model, api_key, session_obj.topic, key_text, mode=mode)

    if not isinstance(result, dict):
        return jsonify({"error": "The AI provider returned an invalid quiz response. Please try again."}), 502
    if "error" in result:
        return jsonify({"error": result["error"]}), 502

    questions = result.get("questions")
    expected_count = 20 if mode == "exam" else 10
    if not isinstance(questions, list) or len(questions) != expected_count:
        return jsonify({"error": result.get("error") or (
            f"The AI provider returned {len(questions) if isinstance(questions, list) else 0} "
            f"of {expected_count} questions. Check your selected provider/model and retry."
        )}), 502
    bloom_by_difficulty = {"easy": "remember", "medium": "apply", "hard": "analyze"}
    bloom_levels = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
    seen_ids = set()
    allowed_types = {"mcq", "msq", "short_answer", "long_answer"}
    allowed_intents = {
        "definition-check", "misconception-trap", "algebraic-hygiene",
        "transfer", "time-pressure",
    }
    for question in questions:
        if not isinstance(question, dict) or not question.get("question"):
            return jsonify({"error": "The AI provider returned an incomplete question. Please generate the quiz again."}), 502
        options = question.get("options")
        answer_type = str(question.get("type", "")).strip().lower()
        if answer_type not in allowed_types:
            answer_type = "msq" if isinstance(question.get("correct"), list) else (
                "mcq" if isinstance(options, dict) and options else "short_answer"
            )
        question["type"] = answer_type
        if not isinstance(options, dict):
            options = {}
        if answer_type in {"mcq", "msq"}:
            correct_answer = question.get("correct")
            valid_keys = set(options)
            valid = (
                isinstance(correct_answer, str) and correct_answer in valid_keys
                if answer_type == "mcq"
                else isinstance(correct_answer, list) and len(correct_answer) >= 2
                and set(correct_answer).issubset(valid_keys)
            )
            if len(options) < 2 or not valid or any(
                not isinstance(key, str) or not isinstance(value, str) or not value.strip()
                for key, value in options.items()
            ):
                return jsonify({"error": "The AI provider returned an invalid objective question. Please generate the quiz again."}), 502
        else:
            reference_answer = question.get("reference_answer")
            rubric = question.get("rubric")
            if (not isinstance(reference_answer, str) or not reference_answer.strip()
                    or not isinstance(rubric, list) or len(rubric) != 3
                    or any(not isinstance(item, str) or not item.strip() for item in rubric)):
                return jsonify({"error": "The AI provider returned an incomplete written-answer rubric. Please generate the quiz again."}), 502
            question["options"] = {}
            question["correct"] = None
        if question.get("id") is None:
            return jsonify({"error": "The AI provider returned a question without an ID. Please generate the quiz again."}), 502
        if not isinstance(question.get("options"), dict):
            return jsonify({"error": "The AI provider returned an incomplete question. Please generate the quiz again."}), 502
        question_id = str(question["id"])
        if question_id in seen_ids:
            return jsonify({"error": "The AI provider returned duplicate quiz questions. Please try again."}), 502
        seen_ids.add(question_id)
        question["difficulty"] = str(question.get("difficulty", "medium")).lower()
        if question["difficulty"] not in bloom_by_difficulty:
            question["difficulty"] = "medium"
        level = str(question.get("bloom_level", "")).strip().lower()
        question["bloom_level"] = level if level in bloom_levels else bloom_by_difficulty.get(
            question["difficulty"], "understand"
        )
        question["explanation"] = str(
            question.get("explanation") or "Compare the correct answer with the reasoning behind each option."
        )
        intent = str(question.get("examiner_intent", "")).strip().lower()
        question["examiner_intent"] = intent if intent in allowed_intents else "definition-check"

    generation_mode = "recall" if mode == "quiz" and due_schedule else mode
    cutoff = datetime.utcnow() - timedelta(days=30)
    QuizGeneration.query.filter(
        QuizGeneration.user_id == current_user.id,
        QuizGeneration.created_at < cutoff,
    ).delete(synchronize_session=False)
    generation_key = secrets.token_urlsafe(32)
    generation = QuizGeneration(
        user_id=current_user.id,
        session_id=session_id,
        generation_key=generation_key,
        mode=generation_mode,
    )
    generation.questions = questions
    db.session.add(generation)
    db.session.commit()
    return jsonify({
        "questions": [
            {
                key: value for key, value in question.items()
                if key not in {"correct", "reference_answer", "rubric"}
            }
            for question in questions
        ],
        "generation_id": generation.id,
        "generation_key": generation_key,
        "mode": generation_mode,
        "recall_cycle": due_schedule.cycle_number if generation_mode == "recall" else None,
    })


@quiz_bp.route("/<int:session_id>/submit", methods=["POST"])
@login_required
def submit(session_id):
    session_obj = LearningSession.query.filter_by(
        id=session_id, user_id=current_user.id).first_or_404()

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Quiz answers could not be read. Please try again."}), 400
    answers = data.get("answers", {})  # {question_id: chosen_option}
    confidence = data.get("confidence", {})
    try:
        generation_id = int(data.get("generation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Quiz generation expired. Generate the questions again."}), 400
    generation = QuizGeneration.query.filter_by(
        id=generation_id,
        user_id=current_user.id,
        session_id=session_id,
    ).first()
    generation_key = data.get("generation_key", "")
    if (not generation or generation.submitted_at
            or not isinstance(generation_key, str)
            or not secrets.compare_digest(generation.generation_key, generation_key)):
        return jsonify({"error": "Quiz generation is invalid or already submitted. Generate it again."}), 400
    mode = generation.mode
    if mode not in {"quiz", "exam", "recall"}:
        return jsonify({"error": "Choose Quiz or Exam mode."}), 400
    if _quiz_limit_reached(session_obj) and mode != "recall":
        return jsonify({"error": "Explorer includes one quiz attempt per session. Upgrade to Scholar for unlimited quiz attempts.",
                        "redirect": url_for("features.pricing")}), 403
    if mode == "exam" and not current_app.config["PRICING"].get(current_user.plan, {}).get("exam_mode", False):
        return jsonify({"error": "Timed exams with negative marking are available on Scholar and Academy.",
                        "redirect": url_for("features.pricing")}), 403
    age_seconds = (datetime.utcnow() - generation.created_at).total_seconds()
    if mode == "exam" and age_seconds > 1815:
        return jsonify({"error": "Time is up. Generate a new exam to try again."}), 400
    if age_seconds > 30 * 24 * 60 * 60:
        return jsonify({"error": "This quiz generation has expired. Generate the questions again."}), 400
    questions = generation.questions
    if (not isinstance(answers, dict) or not isinstance(confidence, dict)
            or not isinstance(questions, list) or not questions or len(questions) > 20
            or any(not isinstance(question, dict) or question.get("id") is None
                   or not isinstance(question.get("options"), dict)
                   or question.get("type", "mcq") not in {"mcq", "msq", "short_answer", "long_answer"}
                   for question in questions)):
        return jsonify({"error": "Quiz questions or answers are invalid. Generate the quiz again."}), 400

    recall_schedule = _due_recall_schedule(session_obj)
    if mode == "recall" and recall_schedule is None:
        return jsonify({"error": "This session has no due 10-day recall check. Refresh the dashboard and try again."}), 400
    try:
        written_scores = evaluate_written_answers(
            current_user.ai_provider,
            current_user.ai_model,
            current_user.get_ai_api_key(),
            session_obj.topic,
            questions,
            answers,
        )
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 502

    correct = 0
    wrong = 0
    points_earned = 0.0
    evaluated = []
    for q in questions:
        qid = str(q["id"])
        answer_type = q.get("type", "mcq")
        user_ans = answers.get(qid, "")
        if answer_type == "msq":
            if not isinstance(user_ans, list):
                user_ans = []
            valid_options = set(q["options"])
            user_ans = list(dict.fromkeys(
                key for key in user_ans if isinstance(key, str) and key in valid_options
            ))
            is_correct = set(user_ans) == set(q.get("correct") or [])
        elif answer_type == "mcq":
            user_ans = user_ans if isinstance(user_ans, str) and user_ans in q["options"] else ""
            is_correct = user_ans == q.get("correct")
        else:
            user_ans = user_ans.strip()[:5000] if isinstance(user_ans, str) else ""
            grade = written_scores.get(qid) if user_ans else None
            if grade:
                points = sum(grade["criteria"]) / 6
                points_earned += points
                is_correct = points >= 1
            else:
                is_correct = False
        if is_correct:
            correct += 1
            if answer_type in {"mcq", "msq"}:
                points_earned += 1
        elif user_ans and answer_type in {"mcq", "msq"}:
            wrong += 1
        try:
            confidence_rating = max(1, min(5, int(confidence[qid]))) if confidence.get(qid) else None
        except (TypeError, ValueError):
            confidence_rating = None
        evaluated.append({
            **q,
            "user_answer": user_ans,
            "is_correct": is_correct,
            "confidence": confidence_rating,
            "earned_points": round(
                sum(written_scores.get(qid, {}).get("criteria", [])) / 6
                if answer_type in {"short_answer", "long_answer"} else (1 if is_correct else 0),
                2,
            ),
            "written_feedback": written_scores.get(qid, {}).get("feedback", ""),
        })

    total = len(questions)
    negative_points = wrong * 0.25 if mode == "exam" else 0
    score = round(max(0, (points_earned - negative_points) / total) * 100, 1) if total else 0
    blueprint = {}
    for question in questions:
        intent = question.get("examiner_intent", "definition-check")
        blueprint[intent] = blueprint.get(intent, 0) + 1
    blueprint_summary = [
        {"intent": intent, "count": count, "percent": round(count * 100 / total)}
        for intent, count in sorted(blueprint.items(), key=lambda item: (-item[1], item[0]))
    ]

    # Save attempt
    attempt = QuizAttempt(
        session_id=session_id,
        score=score,
        total_questions=total,
        correct_answers=correct,
    )
    attempt.questions = evaluated
    db.session.add(attempt)
    now = datetime.utcnow()
    if recall_schedule:
        elapsed_days = max(0.01, (now - recall_schedule.last_test_at).total_seconds() / 86400)
        history = recall_schedule.history
        establishes_baseline = (
            len(history) == 1 and history[0].get("is_baseline_estimate")
        )
        relative_recall = (
            1.0 if establishes_baseline else
            min(1.0, max(0.01, score / max(1.0, recall_schedule.last_score)))
        )
        if not establishes_baseline and relative_recall < 0.98:
            observed_stability = max(1.0, -elapsed_days / math.log(relative_recall))
            recall_schedule.stability_days = (
                observed_stability if recall_schedule.stability_days is None
                else 0.5 * recall_schedule.stability_days + 0.5 * observed_stability
            )
        recall_schedule.baseline_score = score
        history.append({
            "cycle": recall_schedule.cycle_number,
            "elapsed_days": round(elapsed_days, 2),
            "score": score,
            "relative_recall": round(relative_recall * 100, 1),
            "tested_at": now.isoformat(),
            "establishes_baseline": establishes_baseline,
        })
        recall_schedule.history = history[-30:]
        recall_schedule.last_score = score
        recall_schedule.last_test_at = now
        recall_schedule.cycle_number += 1
        recall_schedule.next_test_at = now + timedelta(days=recall_schedule.interval_days)
    elif not SessionRecallSchedule.query.filter_by(
        user_id=current_user.id, session_id=session_id
    ).first():
        recall_schedule = SessionRecallSchedule(
            user_id=current_user.id,
            session_id=session_id,
            cycle_number=1,
            interval_days=10,
            baseline_score=score,
            last_score=score,
            last_test_at=now,
            next_test_at=now + timedelta(days=10),
            history=[{
                "cycle": 0,
                "elapsed_days": 0,
                "score": score,
                "relative_recall": 100,
                "tested_at": now.isoformat(),
            }],
        )
        db.session.add(recall_schedule)
    else:
        existing_schedule = SessionRecallSchedule.query.filter_by(
            user_id=current_user.id, session_id=session_id
        ).first()
        history = existing_schedule.history if existing_schedule else []
        if (existing_schedule and existing_schedule.next_test_at > now
                and len(history) == 1 and history[0].get("is_baseline_estimate")):
            existing_schedule.baseline_score = score
            existing_schedule.last_score = score
            existing_schedule.last_test_at = now
            history[0] = {
                "cycle": 0,
                "elapsed_days": 0,
                "score": score,
                "relative_recall": 100,
                "tested_at": now.isoformat(),
                "is_baseline_estimate": False,
            }
            existing_schedule.history = history
    review = TopicReviewSchedule.query.filter_by(
        user_id=current_user.id, topic_slug=topic_slug(session_obj.topic)
    ).first()
    if score < 70 and review is None:
        review = TopicReviewSchedule(
            user_id=current_user.id,
            topic=session_obj.topic,
            topic_slug=topic_slug(session_obj.topic),
            interval_days=1 if score < 50 else 3,
        )
        db.session.add(review)
    elif score < 80 and review is not None:
        review.topic = session_obj.topic
        review.interval_days = (
            1 if score < 50 else 3 if score < 70 else 7
        )
    if review is not None and score < 80:
        review.next_review_at = datetime.utcnow() + timedelta(days=review.interval_days)
    elif review is not None and score >= 80:
        db.session.delete(review)

    review_url = None
    if total and score < 40:
        # Reopen this completed session for a focused follow-up conversation.
        session_obj.status = "reviewing"
        review_url = url_for("tutor.chat", session_id=session_obj.id, review="latest")

    # Update session quiz score (best score)
    if session_obj.quiz_score is None or score > session_obj.quiz_score:
        session_obj.quiz_score = score
    mastery = None
    if session_obj.status in {"completed", "reviewing"}:
        mastery = recalculate_topic_mastery(
            current_user.id, topic_slug(session_obj.topic)
        )
        if mastery:
            session_obj.mastery_score = mastery.overall
    generation.submitted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "score": score,
        "correct": correct,
        "wrong": wrong,
        "total": total,
        "mode": mode,
        "evaluated": evaluated,
        "blueprint": blueprint_summary,
        "negative_points": negative_points,
        "recall": {
            "cycle_number": recall_schedule.cycle_number,
            "next_test_at": recall_schedule.next_test_at.isoformat(),
            "stability_days": round(recall_schedule.stability_days, 1)
                if recall_schedule.stability_days is not None else None,
        } if recall_schedule else None,
        "attempt_id": attempt.id,
        "review_url": review_url,
        "mastery": mastery.to_dict() if mastery else None,
    })
