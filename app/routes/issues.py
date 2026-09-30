"""Student issue reporting and status tracking."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc

from app import db
from app.models import IssueReport, IssueStatusUpdate

issues_bp = Blueprint("issues", __name__)

ISSUE_CATEGORIES = {
    "bug": "Something is broken",
    "layout": "Layout or accessibility",
    "account": "Account or billing",
    "learning": "Learning tool or content",
    "other": "Other",
}


@issues_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        page = request.form.get("page", "").strip()
        if not title or len(title) > 160:
            flash("Add a short issue title (up to 160 characters).", "error")
        elif category not in ISSUE_CATEGORIES:
            flash("Choose an issue category.", "error")
        elif not description or len(description) > 5000:
            flash("Describe the issue in 1–5,000 characters.", "error")
        elif page and (len(page) > 200 or not page.startswith("/") or page.startswith("//")):
            flash("Enter a valid LearnOrbit page path.", "error")
        else:
            report = IssueReport(
                user_id=current_user.id,
                title=title,
                category=category,
                page=page,
                description=description,
            )
            db.session.add(report)
            db.session.flush()
            db.session.add(IssueStatusUpdate(
                issue_id=report.id,
                status="submitted",
                message="Your report was received and is waiting for review.",
            ))
            db.session.commit()
            flash("Your issue was sent to the LearnOrbit team.", "success")
            return redirect(url_for("issues.index", issue=report.id))

    reports = (IssueReport.query.filter_by(user_id=current_user.id)
               .order_by(desc(IssueReport.updated_at), desc(IssueReport.id)).all())
    history = {
        report.id: (IssueStatusUpdate.query.filter_by(issue_id=report.id)
                    .order_by(IssueStatusUpdate.created_at.asc()).all())
        for report in reports
    }
    selected_report = None
    if request.args.get("issue"):
        try:
            selected_id = int(request.args["issue"])
        except ValueError:
            abort(404)
        selected_report = IssueReport.query.filter_by(
            id=selected_id, user_id=current_user.id
        ).first_or_404()
    return render_template(
        "issues/index.html",
        reports=reports,
        history=history,
        selected_report=selected_report,
        categories=ISSUE_CATEGORIES,
    )


@issues_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        return index()
    return redirect(url_for("issues.index"))
