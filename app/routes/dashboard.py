"""
LearnOrbit Dashboard Routes
"""

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from app.models import LearningSession, TopicMastery, LearningBehavior
from app import db
from app.services.mastery_service import recalculate_all_topic_mastery
from sqlalchemy import desc

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/home")
@login_required
def home():
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

    stats = {
        "total_sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
        "completed_sessions": LearningSession.query.filter_by(
            user_id=current_user.id, status="completed").count(),
        "topics_studied": TopicMastery.query.filter_by(user_id=current_user.id).count(),
        "avg_mastery": round(
            db_avg(TopicMastery, current_user.id) or 0, 1
        ),
        "streak": behavior.streak_days if behavior else 0,
    }
    return render_template(
        "dashboard/home.html",
        recent_sessions=recent_sessions,
        mastery_records=mastery_records,
        behavior=behavior,
        stats=stats,
    )


@dashboard_bp.route("/api/stats")
@login_required
def api_stats():
    mastery = TopicMastery.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        "mastery": [m.to_dict() for m in mastery],
        "sessions": LearningSession.query.filter_by(user_id=current_user.id).count(),
    })


def db_avg(model, user_id):
    from app import db
    from sqlalchemy import func
    result = db.session.query(func.avg(model.overall)).filter_by(user_id=user_id).scalar()
    return result
