"""
LearnOrbit Dashboard Routes
"""

from flask import Blueprint, render_template, jsonify, current_app, url_for
from flask_login import login_required, current_user
from app.models import (
    AttendanceStamp,
    GameUsage,
    LearningBehavior,
    LearningSession,
    QuizAttempt,
    SessionRecallSchedule,
    TopicReviewSchedule,
    TopicMastery,
)
from app import db
from app.services.mastery_service import recalculate_all_topic_mastery, topic_slug
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import calendar as pycalendar
import math
import re

dashboard_bp = Blueprint("dashboard", __name__)


def _ensure_recall_schedules(user_id):
    sessions = LearningSession.query.filter(
        LearningSession.user_id == user_id,
        LearningSession.status.in_(("completed", "reviewing")),
    ).all()
    scheduled_ids = {
        session_id for (session_id,) in db.session.query(
            SessionRecallSchedule.session_id
        ).filter_by(user_id=user_id).all()
    }
    created = False
    for session in sessions:
        if session.id in scheduled_ids:
            continue
        completed_at = session.ended_at or session.started_at or datetime.utcnow()
        baseline_score = float(session.quiz_score if session.quiz_score is not None else 100)
        db.session.add(SessionRecallSchedule(
            user_id=user_id,
            session_id=session.id,
            cycle_number=1,
            interval_days=10,
            baseline_score=baseline_score,
            last_score=baseline_score,
            last_test_at=completed_at,
            next_test_at=completed_at + timedelta(days=10),
            history=[{
                "cycle": 0,
                "elapsed_days": 0,
                "score": baseline_score,
                "relative_recall": 100,
                "tested_at": completed_at.isoformat(),
                "is_baseline_estimate": session.quiz_score is None,
            }],
        ))
        created = True
    if created:
        db.session.commit()


@dashboard_bp.route("/")
@dashboard_bp.route("/home")
@login_required
def home():
    from datetime import date
    # Reconcile records created by earlier scoring logic with saved quiz results.
    recalculate_all_topic_mastery(current_user.id)
    db.session.commit()

    recent_sessions = (
        LearningSession.query
        .filter_by(user_id=current_user.id)
        .order_by(desc(LearningSession.started_at))
        .limit(5).all()
    )
    mastery_records = (
        TopicMastery.query
        .filter_by(user_id=current_user.id)
        .order_by(desc(TopicMastery.overall))
        .limit(8).all()
    )
    behavior = LearningBehavior.query.filter_by(user_id=current_user.id).first()
    scheduled_reviews = (TopicReviewSchedule.query.filter_by(user_id=current_user.id)
                         .order_by(TopicReviewSchedule.next_review_at.asc()).all())
    review_rows = []
    for review in scheduled_reviews:
        latest_review_attempt = (
            QuizAttempt.query.join(LearningSession)
            .filter(
                LearningSession.user_id == current_user.id,
                LearningSession.topic == review.topic,
            )
            .order_by(QuizAttempt.attempted_at.desc())
            .first()
        )
        if latest_review_attempt and (latest_review_attempt.score or 0) >= 80:
            db.session.delete(review)
            continue
        if latest_review_attempt is None:
            continue
        review_rows.append({
            "schedule": review,
            "score": round(latest_review_attempt.score or 0),
            "session_id": latest_review_attempt.session_id,
        })
    if len(review_rows) != len(scheduled_reviews):
        db.session.commit()
    review_rows = review_rows[:6]
    scheduled_reviews = [row["schedule"] for row in review_rows]
    review_context = {
        row["schedule"].id: row for row in review_rows
    }
    _ensure_recall_schedules(current_user.id)
    session_recall_rows = (SessionRecallSchedule.query.join(
        LearningSession, SessionRecallSchedule.session_id == LearningSession.id
    ).filter(
        SessionRecallSchedule.user_id == current_user.id,
        LearningSession.status.in_(("completed", "reviewing")),
    ).options(joinedload(SessionRecallSchedule.session))
     .order_by(SessionRecallSchedule.next_test_at.asc()).all())
    recall_sessions = []
    recall_chart_labels = list(range(0, 31, 2))
    recall_chart_datasets = []
    for schedule in session_recall_rows:
        session = schedule.session
        recall_sessions.append({
            "session_id": session.id,
            "topic": session.topic,
            "cycle_number": schedule.cycle_number,
            "next_test_at": schedule.next_test_at,
            "last_score": schedule.last_score,
            "stability_days": schedule.stability_days,
            "baseline_estimated": bool(
                len(schedule.history) == 1
                and schedule.history[0].get("is_baseline_estimate")
            ),
            "due": schedule.next_test_at <= datetime.utcnow(),
        })
        if schedule.stability_days and schedule.stability_days > 0:
            recall_chart_datasets.append({
                "label": session.topic[:40],
                "data": [
                    round(schedule.baseline_score * math.exp(-day / schedule.stability_days), 1)
                    for day in recall_chart_labels
                ],
            })
    today = date.today()
    last_attendance = AttendanceStamp.query.filter(
        AttendanceStamp.user_id == current_user.id,
        AttendanceStamp.attended_on <= today,
    ).order_by(AttendanceStamp.attended_on.desc()).all()
    streak = 0
    expected_day = (
        today if last_attendance and last_attendance[0].attended_on == today
        else today - timedelta(days=1)
    )
    for attendance_row in last_attendance:
        if attendance_row.attended_on != expected_day:
            break
        streak += 1
        expected_day -= timedelta(days=1)
    attendance = AttendanceStamp.query.filter_by(user_id=current_user.id).filter(
        AttendanceStamp.attended_on >= today.replace(day=1),
        AttendanceStamp.attended_on <= today).count()
    attendance_days = sorted({row.attended_on.day for row in AttendanceStamp.query.filter_by(user_id=current_user.id).filter(
        AttendanceStamp.attended_on >= today.replace(day=1), AttendanceStamp.attended_on <= today).all()}
    )
    yearly_attendance = AttendanceStamp.query.filter_by(user_id=current_user.id).filter(
        AttendanceStamp.attended_on >= today.replace(month=1, day=1),
        AttendanceStamp.attended_on <= today).count()
    # Real study activity, grouped by local calendar day, for the last two weeks.
    analytics_days = [today - timedelta(days=13 - i) for i in range(14)]
    session_rows = LearningSession.query.filter(
        LearningSession.user_id == current_user.id,
        LearningSession.started_at >= datetime.combine(analytics_days[0], datetime.min.time()),
        LearningSession.started_at < datetime.combine(today + timedelta(days=1), datetime.min.time()),
    ).all()
    activity_by_day = {}
    for row in session_rows:
        key = row.started_at.date()
        activity_by_day[key] = activity_by_day.get(key, 0) + 1
    quiz_rows = (QuizAttempt.query.join(LearningSession).filter(
        LearningSession.user_id == current_user.id,
        QuizAttempt.attempted_at >= datetime.combine(analytics_days[0], datetime.min.time()),
        QuizAttempt.attempted_at < datetime.combine(today + timedelta(days=1), datetime.min.time()),
    ).all())
    review_attempts = (
        QuizAttempt.query.join(LearningSession)
        .filter(LearningSession.user_id == current_user.id)
        .order_by(QuizAttempt.attempted_at.desc())
        .limit(100)
        .all()
    )
    quiz_by_day = {}
    for row in quiz_rows:
        key = row.attempted_at.date()
        quiz_by_day.setdefault(key, []).append(float(row.score or 0))
    confidence_observations = [
        (int(question["confidence"]) * 20, 100 if question.get("is_correct") else 0)
        for attempt in quiz_rows
        for question in attempt.questions
        if str(question.get("confidence", "")).isdigit()
    ]
    total_retrieval_questions = sum(
        len(attempt.questions) for attempt in quiz_rows
    )
    correct_retrieval_questions = sum(
        sum(bool(question.get("is_correct")) for question in attempt.questions)
        for attempt in quiz_rows
    )
    weekly_days = [today - timedelta(days=6 - i) for i in range(7)]
    weekly_sessions = LearningSession.query.filter(
        LearningSession.user_id == current_user.id,
        LearningSession.started_at >= datetime.combine(weekly_days[0], datetime.min.time()),
        LearningSession.started_at < datetime.combine(today + timedelta(days=1), datetime.min.time()),
    ).all()
    weekly_games = GameUsage.query.filter(
        GameUsage.user_id == current_user.id,
        GameUsage.started_at >= datetime.combine(weekly_days[0], datetime.min.time()),
        GameUsage.started_at < datetime.combine(today + timedelta(days=1), datetime.min.time()),
    ).all()
    weekly_minutes = {day: {"study": 0, "games": 0} for day in weekly_days}
    for row in weekly_sessions:
        minutes = max(0, min(240, ((row.ended_at or datetime.utcnow()) - row.started_at).total_seconds() / 60))
        weekly_minutes[row.started_at.date()]["study"] += round(minutes)
    for row in weekly_games:
        # An unclosed game tab cannot accrue more than the application's 15-minute limit.
        ended = row.ended_at or min(datetime.utcnow(), row.started_at + timedelta(minutes=15))
        minutes = max(0, min(15, (ended - row.started_at).total_seconds() / 60))
        weekly_minutes[row.started_at.date()]["games"] += round(minutes)
    weekly_activity = [
        {"label": day.strftime("%a"), **weekly_minutes[day],
         "total": weekly_minutes[day]["study"] + weekly_minutes[day]["games"]}
        for day in weekly_days
    ]
    weak_counts = {}
    def add_misconception(
        label, topic, session_id, source, correction=None,
        confidence=None, attempt_id=None, attempted_at=None,
    ):
        label = str(label or "").strip()
        if not label:
            return
        normalized = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
        if not normalized:
            return
        key = (topic_slug(topic), normalized)
        entry = weak_counts.setdefault(key, {
            "label": label[:180],
            "attempt_ids": set(),
            "confident_misses": 0,
            "tutor_signals": 0,
            "topic": topic,
            "session_id": session_id,
            "source": source,
            "correction": correction,
            "last_seen": attempted_at,
        })
        if attempt_id is not None:
            entry["attempt_ids"].add(attempt_id)
            try:
                if int(confidence) >= 4:
                    entry["confident_misses"] += 1
            except (TypeError, ValueError):
                pass
        elif source == "tutor":
            entry["tutor_signals"] += 1
        if attempted_at and (
            entry["last_seen"] is None or attempted_at > entry["last_seen"]
        ):
            entry["last_seen"] = attempted_at
            entry["session_id"] = session_id
        if correction and not entry["correction"]:
            entry["correction"] = correction

    for attempt in review_attempts:
        for question in attempt.questions:
            if question.get("is_correct"):
                continue
            add_misconception(
                question.get("misconception_check") or question.get("question"),
                attempt.session.topic, attempt.session_id, "assessment",
                confidence=question.get("confidence"),
                attempt_id=attempt.id,
                attempted_at=attempt.attempted_at,
            )
    for session in LearningSession.query.filter_by(user_id=current_user.id).all():
        for misconception in session.misconceptions:
            if not isinstance(misconception, dict):
                continue
            try:
                confidence = float(misconception.get("confidence") or 0)
            except (TypeError, ValueError):
                continue
            if math.isfinite(confidence) and confidence >= 0.8:
                add_misconception(
                    misconception.get("text"),
                    misconception.get("topic") or session.topic,
                    session.id,
                    "tutor",
                    misconception.get("correction"),
                    attempted_at=session.ended_at or session.started_at,
                )
    weak_concepts = []
    for concept in weak_counts.values():
        assessment_attempts = len(concept["attempt_ids"])
        if not (
            assessment_attempts >= 2
            or concept["confident_misses"]
            or concept["tutor_signals"]
        ):
            continue
        concept["signals"] = assessment_attempts + concept["confident_misses"] + concept["tutor_signals"]
        if concept["tutor_signals"]:
            concept["reason"] = "Tutor flagged a likely misconception"
            concept["source"] = "tutor"
        elif concept["confident_misses"]:
            concept["reason"] = "Incorrect despite high confidence"
        else:
            concept["reason"] = f"Missed in {assessment_attempts} separate quizzes"
        concept.pop("attempt_ids")
        weak_concepts.append(concept)
    weak_concepts.sort(
        key=lambda row: (
            row["signals"],
            row["last_seen"] or datetime.min,
        ),
        reverse=True,
    )
    weak_concepts = weak_concepts[:5]
    weekly_peak = max((row["total"] for row in weekly_activity), default=0)
    analytics = {
        "labels": [day.strftime("%d %b") for day in analytics_days],
        "sessions": [activity_by_day.get(day, 0) for day in analytics_days],
        "quiz": [round(sum(quiz_by_day[day]) / len(quiz_by_day[day]), 1) if quiz_by_day.get(day) else None for day in analytics_days],
        "quiz_count": len(quiz_rows),
        "average_quiz": round(sum(float(row.score or 0) for row in quiz_rows) / len(quiz_rows), 1) if quiz_rows else None,
        "confidence": round(sum(confidence for confidence, _ in confidence_observations) / len(confidence_observations), 1) if confidence_observations else None,
        "calibration": round(100 - sum(abs(confidence - outcome) for confidence, outcome in confidence_observations) / len(confidence_observations), 1) if confidence_observations else None,
        "recall": round(100 * correct_retrieval_questions / total_retrieval_questions, 1) if total_retrieval_questions else None,
        "weekly_activity": weekly_activity,
        "weekly_peak": weekly_peak,
        "weak_concepts": weak_concepts,
        "confidence_answers": len(confidence_observations),
        "retrieval_questions": total_retrieval_questions,
    }
    analytics_unlocked = current_app.config["PRICING"].get(current_user.plan, {}).get("analytics_dashboard", False)
    if not analytics_unlocked:
        analytics.update(confidence=None, calibration=None, recall=None, confidence_answers=0, retrieval_questions=0)

    stats = {
        "total_sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
        "completed_sessions": LearningSession.query.filter_by(
            user_id=current_user.id, status="completed").count(),
        "topics_studied": TopicMastery.query.filter_by(user_id=current_user.id).count(),
        "avg_mastery": round(
            db_avg(TopicMastery, current_user.id) or 0, 1
        ),
        "streak": streak,
        "attendance_month": attendance,
        "attendance_year": yearly_attendance,
        "attendance_days": attendance_days,
        "month_days": pycalendar.monthrange(today.year, today.month)[1],
    }
    return render_template(
        "dashboard/home.html",
        recent_sessions=recent_sessions,
        mastery_records=mastery_records,
        behavior=behavior,
        stats=stats,
        analytics=analytics,
        scheduled_reviews=scheduled_reviews,
        review_context=review_context,
        recall_sessions=recall_sessions,
        recall_chart={
            "labels": recall_chart_labels,
            "datasets": recall_chart_datasets[:8],
        },
        now_utc=datetime.utcnow(),
        analytics_unlocked=analytics_unlocked,
    )


@dashboard_bp.route("/api/stats")
@login_required
def api_stats():
    mastery = TopicMastery.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        "mastery": [m.to_dict() for m in mastery],
        "sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
    })


@dashboard_bp.route("/api/reviews")
@login_required
def due_reviews():
    now = datetime.utcnow()
    due = (TopicReviewSchedule.query.filter_by(user_id=current_user.id)
           .filter(TopicReviewSchedule.next_review_at <= now)
           .order_by(TopicReviewSchedule.next_review_at.asc()).limit(10).all())
    return jsonify({"reviews": [
        {"id": row.id, "topic": row.topic, "next_review_at": row.next_review_at.isoformat()}
        for row in due
    ]})


@dashboard_bp.route("/api/recall-due")
@login_required
def due_recall_checks():
    _ensure_recall_schedules(current_user.id)
    now = datetime.utcnow()
    rows = (SessionRecallSchedule.query.join(
        LearningSession, SessionRecallSchedule.session_id == LearningSession.id
    ).filter(
        SessionRecallSchedule.user_id == current_user.id,
        SessionRecallSchedule.next_test_at <= now,
        LearningSession.status.in_(("completed", "reviewing")),
    ).order_by(SessionRecallSchedule.next_test_at.asc()).limit(30).all())
    return jsonify({"checks": [
        {
            "session_id": row.session_id,
            "topic": row.session.topic,
            "cycle_number": row.cycle_number,
            "url": url_for("quiz.quiz_page", session_id=row.session_id),
        }
        for row in rows
    ]})


@dashboard_bp.route("/api/reviews/<int:schedule_id>/complete", methods=["POST"])
@login_required
def complete_review(schedule_id):
    schedule = TopicReviewSchedule.query.filter_by(
        id=schedule_id, user_id=current_user.id
    ).first_or_404()
    latest_attempt = (QuizAttempt.query.join(LearningSession)
                      .filter(LearningSession.user_id == current_user.id,
                              LearningSession.topic == schedule.topic)
                      .order_by(QuizAttempt.attempted_at.desc()).first())
    schedule.repetitions += 1
    if latest_attempt and latest_attempt.score is not None and latest_attempt.score < 60:
        schedule.interval_days = 1
    else:
        schedule.interval_days = min(30, max(1, round(schedule.interval_days * 2.1)))
    schedule.last_reviewed_at = datetime.utcnow()
    schedule.next_review_at = schedule.last_reviewed_at + timedelta(days=schedule.interval_days)
    db.session.commit()
    return jsonify({"success": True, "next_review_at": schedule.next_review_at.isoformat(),
                    "interval_days": schedule.interval_days})


@dashboard_bp.route("/api/topic-map", methods=["POST"])
@login_required
def topic_map():
    import json
    from app.services.ai_service import call_ai, _parse_json_payload
    topics = [row.topic for row in TopicMastery.query.filter_by(user_id=current_user.id).order_by(TopicMastery.last_studied.desc()).limit(16).all()]
    topics = list(dict.fromkeys(topic.strip() for topic in topics if topic.strip()))
    edges = []
    key = current_user.get_ai_api_key()
    if len(topics) > 1 and key:
        try:
            prompt = ("Given these student learning topics, return strict JSON with `contains` (array of {parent,child}) and `related` (array of {from,to,label}). "
                      "Use only exact topic names from this list. Contains means one is a subtopic of another; related means distinct concepts with a useful connection. "
                      "Do not invent topics. Topics: " + json.dumps(topics))
            raw = call_ai(current_user.ai_provider, current_user.ai_model, key, [{"role":"user","content":prompt}], max_tokens=900)
            payload = _parse_json_payload(raw)
            if not isinstance(payload, dict):
                raise ValueError("Topic map response was not valid JSON.")
            for kind, items in (("contains", payload.get("contains", [])), ("related", payload.get("related", []))):
                if not isinstance(items, list):
                    continue
                for item in items[:60]:
                    if not isinstance(item, dict):
                        continue
                    source, target = (item.get("parent"), item.get("child")) if kind == "contains" else (item.get("from"), item.get("to"))
                    if source in topics and target in topics and source != target:
                        edges.append({"source":source,"target":target,"kind":kind,"label":str(item.get("label", "part of" if kind=="contains" else "related"))[:48]})
        except (ValueError, TypeError, AttributeError, KeyError) as error:
            current_app.logger.info("Topic map model response could not be parsed: %s", type(error).__name__)
        except Exception as error:
            current_app.logger.warning("Topic map generation failed: %s", type(error).__name__)
    if len(topics) > 1 and not edges:
        stop_words = {
            "a", "an", "and", "as", "at", "by", "for", "from", "how", "in",
            "intro", "introduction", "of", "on", "or", "overview", "the", "to",
            "with", "basics", "fundamentals",
        }
        normalized = {
            topic: {
                token for token in re.findall(r"[a-z0-9]+", topic.lower())
                if len(token) > 1 and token not in stop_words
            }
            for topic in topics
        }
        edge_pairs = set()
        for index, topic in enumerate(topics):
            for other in topics[index + 1:]:
                left, right = normalized[topic], normalized[other]
                shared = left & right
                if not left or not right:
                    continue
                if left < right or right < left:
                    parent, child = (topic, other) if left < right else (other, topic)
                    edge_pairs.add((parent, child, "contains"))
                    edges.append({"source": parent, "target": child, "kind": "contains", "label": "subtopic"})
                else:
                    similarity = len(shared) / len(left | right)
                    pair = tuple(sorted((topic, other)))
                    if len(shared) >= 2 and similarity >= 0.35 and pair not in edge_pairs:
                        edge_pairs.add(pair)
                        edges.append({"source": topic, "target": other, "kind": "related", "label": "shared concepts"})
                if len(edges) >= 32:
                    break
            if len(edges) >= 32:
                break
    return jsonify({"topics":topics,"edges":edges,"generated_by":current_user.ai_provider if key and edges else "topic-overlap" if edges else None,
                    "message":None if edges else "Study a few related topics to reveal connections."})


def db_avg(model, user_id):
    from app import db
    from sqlalchemy import func
    result = db.session.query(func.avg(model.overall)).filter_by(user_id=user_id).scalar()
    return result
