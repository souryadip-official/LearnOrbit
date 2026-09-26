"""
LearnOrbit Dashboard Routes
"""

from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from app.models import LearningSession, TopicMastery, LearningBehavior, AttendanceStamp, QuizAttempt
from app import db
from app.services.mastery_service import recalculate_all_topic_mastery
from sqlalchemy import desc
from datetime import datetime, timedelta
import calendar as pycalendar

dashboard_bp = Blueprint("dashboard", __name__)


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
    today = date.today()
    attendance = AttendanceStamp.query.filter_by(user_id=current_user.id).filter(
        AttendanceStamp.attended_on >= today.replace(day=1),
        AttendanceStamp.attended_on <= today).count()
    attendance_days = {row.attended_on.day for row in AttendanceStamp.query.filter_by(user_id=current_user.id).filter(
        AttendanceStamp.attended_on >= today.replace(day=1), AttendanceStamp.attended_on <= today).all()}
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
    quiz_by_day = {}
    for row in quiz_rows:
        key = row.attempted_at.date()
        quiz_by_day.setdefault(key, []).append(float(row.score or 0))
    analytics = {
        "labels": [day.strftime("%d %b") for day in analytics_days],
        "sessions": [activity_by_day.get(day, 0) for day in analytics_days],
        "quiz": [round(sum(quiz_by_day[day]) / len(quiz_by_day[day]), 1) if quiz_by_day.get(day) else None for day in analytics_days],
        "quiz_count": len(quiz_rows),
        "average_quiz": round(sum(float(row.score or 0) for row in quiz_rows) / len(quiz_rows), 1) if quiz_rows else None,
    }

    stats = {
        "total_sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
        "completed_sessions": LearningSession.query.filter_by(
            user_id=current_user.id, status="completed").count(),
        "topics_studied": TopicMastery.query.filter_by(user_id=current_user.id).count(),
        "avg_mastery": round(
            db_avg(TopicMastery, current_user.id) or 0, 1
        ),
        "streak": behavior.streak_days if behavior else 0,
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
    )


@dashboard_bp.route("/api/stats")
@login_required
def api_stats():
    mastery = TopicMastery.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        "mastery": [m.to_dict() for m in mastery],
        "sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
    })


@dashboard_bp.route("/api/topic-map", methods=["POST"])
@login_required
def topic_map():
    import json, re
    from app.services.ai_service import call_ai
    topics = [row.topic for row in TopicMastery.query.filter_by(user_id=current_user.id).order_by(TopicMastery.last_studied.desc()).limit(36).all()]
    topics = list(dict.fromkeys(topic.strip() for topic in topics if topic.strip()))
    edges = []
    key = current_user.get_ai_api_key()
    if len(topics) > 1 and key:
        prompt = ("Given these student learning topics, return strict JSON with `contains` (array of {parent,child}) and `related` (array of {from,to,label}). "
                  "Use only exact topic names from this list. Contains means one is a subtopic of another; related means distinct concepts with a useful connection. "
                  "Do not invent topics. Topics: " + json.dumps(topics))
        raw = call_ai(current_user.ai_provider, current_user.ai_model, key, [{"role":"user","content":prompt}], max_tokens=900)
        try:
            payload = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.I).strip())
            for kind, items in (("contains", payload.get("contains", [])), ("related", payload.get("related", []))):
                for item in items[:60]:
                    source, target = (item.get("parent"), item.get("child")) if kind == "contains" else (item.get("from"), item.get("to"))
                    if source in topics and target in topics and source != target:
                        edges.append({"source":source,"target":target,"kind":kind,"label":str(item.get("label", "part of" if kind=="contains" else "related"))[:48]})
        except (ValueError, TypeError, AttributeError):
            current_app.logger.info("Topic map model response could not be parsed")
    return jsonify({"topics":topics,"edges":edges,"generated_by":current_user.ai_provider if key else None,
                    "message":None if key else "Add your AI provider key in Settings to discover topic connections."})


def db_avg(model, user_id):
    from app import db
    from sqlalchemy import func
    result = db.session.query(func.avg(model.overall)).filter_by(user_id=user_id).scalar()
    return result
