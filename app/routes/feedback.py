"""Anonymous product feedback and public aggregate ratings."""

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from sqlalchemy import func

from app import db
from app.models import ProductFeedback

feedback_bp = Blueprint("feedback", __name__)

RATING_FIELDS = {
    "ease_rating": ("Ease of use", "How easy was it to find your way around LearnOrbit?"),
    "learning_rating": ("Learning value", "How useful was LearnOrbit for understanding and practicing?"),
    "reliability_rating": ("Reliability", "How reliably did pages and learning tools work?"),
    "design_rating": ("Design", "How clear and comfortable was the visual experience?"),
    "overall_rating": ("Overall experience", "Overall, how satisfied are you with LearnOrbit?"),
}
PUBLIC_FEEDBACK_MINIMUM = 5


def public_feedback_summary():
    averages = db.session.query(
        func.avg(ProductFeedback.ease_rating),
        func.avg(ProductFeedback.learning_rating),
        func.avg(ProductFeedback.reliability_rating),
        func.avg(ProductFeedback.design_rating),
        func.avg(ProductFeedback.overall_rating),
        func.count(ProductFeedback.id),
    ).one()
    count = int(averages[5] or 0)
    fields = list(RATING_FIELDS)
    ratings = {
        field: round(float(averages[index] or 0), 1)
        for index, field in enumerate(fields)
    }
    return {
        "count": count,
        "ratings": ratings,
        "visible": count >= PUBLIC_FEEDBACK_MINIMUM,
        "minimum": PUBLIC_FEEDBACK_MINIMUM,
    }


@feedback_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if request.form.get("website", "").strip():
            return redirect(url_for("feedback.index", submitted="1"))

        ratings = {}
        for field in RATING_FIELDS:
            try:
                value = int(request.form.get(field, ""))
            except (TypeError, ValueError):
                value = 0
            if value not in range(1, 6):
                return render_template(
                    "feedback/index.html",
                    aspects=RATING_FIELDS,
                    error="Please choose a star rating for each question.",
                    summary=public_feedback_summary(),
                ), 400
            ratings[field] = value

        comment = request.form.get("comment", "").strip()
        if len(comment) > 1000:
            return render_template(
                "feedback/index.html",
                aspects=RATING_FIELDS,
                error="Suggestions must be no more than 1,000 characters.",
                summary=public_feedback_summary(),
            ), 400

        db.session.add(ProductFeedback(**ratings, comment=comment or None))
        db.session.commit()
        return redirect(url_for("feedback.index", submitted="1"))

    return render_template(
        "feedback/index.html",
        aspects=RATING_FIELDS,
        summary=public_feedback_summary(),
        submitted=request.args.get("submitted") == "1",
    )
