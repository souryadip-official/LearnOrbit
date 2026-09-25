"""Recalculate topic mastery from completed learning sessions."""

from app import db
from app.models import LearningSession, TopicMastery


def topic_slug(topic: str) -> str:
    return topic.lower().replace(" ", "-")[:100]


def recalculate_topic_mastery(user_id: int, slug: str) -> TopicMastery | None:
    """Keep mastery consistent with the user's completed session results.

    A session contributes its best quiz percentage. If it has no quiz result,
    its conversation engagement contributes a modest score (0–30). Topic
    mastery is the average of those session scores, so a perfect quiz yields
    100% for that session and a later session can raise or lower the average.
    """
    completed = LearningSession.query.filter_by(
        user_id=user_id, status="completed"
    ).all()
    sessions = [session for session in completed if topic_slug(session.topic) == slug]
    if not sessions:
        return None

    mastery = TopicMastery.query.filter_by(user_id=user_id, topic_slug=slug).first()
    if mastery is None:
        mastery = TopicMastery(
            user_id=user_id,
            topic=sessions[0].topic,
            topic_slug=slug,
        )
        db.session.add(mastery)

    scores = []
    for session in sessions:
        if session.quiz_score is not None:
            score = float(session.quiz_score)
        else:
            score = min((session.messages_count or 0) / 20.0, 1.0) * 30
        scores.append(max(0.0, min(100.0, score)))

    average_score = round(sum(scores) / len(scores), 1)
    # Quiz results do not distinguish these dimensions, so use the same
    # evidence-based estimate for each rather than inventing separate scores.
    mastery.understanding = average_score
    mastery.application = average_score
    mastery.problem_solving = average_score
    mastery.retention = average_score
    mastery.sessions_count = len(sessions)
    mastery.last_studied = max(
        (session.ended_at or session.started_at for session in sessions),
        default=None,
    )
    mastery.recalculate_overall()
    return mastery


def recalculate_all_topic_mastery(user_id: int) -> None:
    """Repair and refresh all of a user's topic scores from saved sessions."""
    completed = LearningSession.query.filter_by(
        user_id=user_id, status="completed"
    ).all()
    slugs = {topic_slug(session.topic) for session in completed}
    for slug in slugs:
        recalculate_topic_mastery(user_id, slug)
