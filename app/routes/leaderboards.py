"""Anonymous, evidence-based academic cohort statistics."""

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models import LearningSession, QuizAttempt, TopicMastery, User
from app import db

leaderboards_bp = Blueprint("leaderboards", __name__)


@leaderboards_bp.route("/academics")
@login_required
def academics():
    attempts = (
        db.session.query(QuizAttempt.score, QuizAttempt.attempted_at, LearningSession.user_id)
        .join(LearningSession, QuizAttempt.session_id == LearningSession.id)
        .join(User, LearningSession.user_id == User.id)
        .filter(QuizAttempt.score.isnot(None))
        .all()
    )
    learner_scores = defaultdict(list)
    weekly_scores = defaultdict(lambda: defaultdict(list))
    total_attempts = 0
    today = date.today()
    first_week = today - timedelta(days=today.weekday() + 49)
    week_starts = [first_week + timedelta(days=7 * index) for index in range(8)]
    week_labels = [start.strftime("%b %d") for start in week_starts]

    for score, attempted_at, user_id in attempts:
        score = max(0.0, min(100.0, float(score)))
        learner_scores[user_id].append(score)
        total_attempts += 1
        if attempted_at:
            week_start = attempted_at.date() - timedelta(days=attempted_at.weekday())
            if week_start in week_starts:
                weekly_scores[week_start][user_id].append(score)

    learner_averages = sorted(
        (
            {"average": mean(scores), "attempts": len(scores), "user_id": user_id}
            for user_id, scores in learner_scores.items()
        ),
        key=lambda learner: (-learner["average"], -learner["attempts"]),
    )
    cohort_scores = [learner["average"] for learner in learner_averages]
    student_count = len(cohort_scores)
    cohort_average = mean(cohort_scores) if cohort_scores else None
    cohort_median = median(cohort_scores) if cohort_scores else None
    strong_share = (
        round(sum(score >= 80 for score in cohort_scores) * 100 / student_count)
        if student_count else None
    )

    bands = [
        {"label": "Needs practice", "count": 0, "color": "#e76f51"},
        {"label": "Developing", "count": 0, "color": "#f4a261"},
        {"label": "Proficient", "count": 0, "color": "#2a9d8f"},
        {"label": "Strong", "count": 0, "color": "#4361ee"},
    ]
    for score in cohort_scores:
        band_index = 0 if score < 50 else 1 if score < 70 else 2 if score < 85 else 3
        bands[band_index]["count"] += 1
    for band in bands:
        band["width"] = round(100 * band["count"] / student_count, 1) if student_count else 0

    weekly_trend = []
    for week_start, label in zip(week_starts, week_labels):
        per_learner = [
            mean(scores) for scores in weekly_scores[week_start].values()
        ]
        weekly_trend.append({
            "label": label,
            "average": round(mean(per_learner), 1) if per_learner else None,
            "learners": len(per_learner),
        })

    topic_rows = (
        db.session.query(
            TopicMastery.topic,
            db.func.avg(TopicMastery.overall),
            db.func.count(db.func.distinct(TopicMastery.user_id)),
        )
        .join(User, TopicMastery.user_id == User.id)
        .group_by(TopicMastery.topic)
        .order_by(db.func.count(db.func.distinct(TopicMastery.user_id)).desc())
        .limit(8)
        .all()
    )
    topic_stats = [
        {
            "topic": topic,
            "average": round(float(score or 0), 1),
            "learners": int(learners),
        }
        for topic, score, learners in topic_rows
    ]
    max_topic_learners = max((row["learners"] for row in topic_stats), default=0)
    for topic in topic_stats:
        topic["width"] = round(100 * topic["learners"] / max_topic_learners) if max_topic_learners else 0

    current_rank = next(
        (rank for rank, learner in enumerate(learner_averages, 1)
         if learner["user_id"] == current_user.id),
        None,
    )
    top_score = max(
        (learner["average"] for learner in learner_averages[:10]),
        default=0,
    )
    rankings = [
        {
            "label": f"Learner {rank}",
            "average": round(learner["average"], 1),
            "attempts": learner["attempts"],
            "width": round(100 * learner["average"] / top_score) if top_score else 0,
        }
        for rank, learner in enumerate(learner_averages[:10], 1)
    ]
    return render_template(
        "leaderboards/academics.html",
        stats={
            "student_count": student_count,
            "attempts": total_attempts,
            "average": round(cohort_average, 1) if cohort_average is not None else None,
            "median": round(cohort_median, 1) if cohort_median is not None else None,
            "strong_share": strong_share,
            "current_rank": current_rank,
            "current_score": (
                round(learner_averages[current_rank - 1]["average"], 1)
                if current_rank is not None else None
            ),
        },
        bands=bands,
        weekly_trend=weekly_trend,
        topics=topic_stats,
        rankings=rankings,
    )
