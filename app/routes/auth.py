"""
LearnOrbit Authentication Routes
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, LearningBehavior, UserProfile
from datetime import datetime
from sqlalchemy import func, select

auth_bp = Blueprint("auth", __name__)


def _next_safe_user_id():
    """Avoid reusing IDs still referenced by orphaned rows in old SQLite DBs."""
    maximum = db.session.execute(select(func.max(User.id))).scalar_one_or_none() or 0
    for table in db.metadata.tables.values():
        user_id_column = table.c.get("user_id")
        if user_id_column is None:
            continue
        referenced_id = db.session.execute(select(func.max(user_id_column))).scalar_one_or_none()
        if referenced_id is not None:
            maximum = max(maximum, referenced_id)
    return maximum + 1


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        full_name = data.get("full_name", "").strip()
        date_of_birth = data.get("date_of_birth", "")[:10]
        grade = data.get("grade", "")
        teaching_style = data.get("teaching_style", "balanced")
        desired_plan = data.get("desired_plan", "free")

        errors = []
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if not email or "@" not in email:
            errors.append("Valid email required.")
        if not password or len(password) < 10 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password) or not any(not c.isalnum() for c in password):
            errors.append("Use at least 10 characters with an uppercase letter, a number, and a symbol.")
        if grade and grade not in {"Primary school", "Middle school", "High school", "Undergraduate", "Masters", "Doctorate / PhD"}:
            errors.append("Choose a valid current study level.")
        if teaching_style not in {"balanced", "visual", "analytical", "narrative"}:
            errors.append("Choose a valid teaching style.")
        if desired_plan not in {"free", "pro", "team"}:
            errors.append("Choose a valid plan preference.")
        if User.query.filter_by(username=username).first():
            errors.append("Username already taken.")
        if User.query.filter_by(email=email).first():
            errors.append("Email already registered.")

        if errors:
            if request.is_json:
                return jsonify({"success": False, "errors": errors}), 400
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html")

        user = User(username=username, email=email)
        # Older SQLite databases can retain child rows after an interrupted or
        # manually deleted signup. Do not recycle an ID those rows still use.
        user.id = _next_safe_user_id()
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Older local databases can contain a behavior row left behind by an
        # interrupted signup (SQLite may not have enforced the old FK). Reuse
        # it instead of violating the unique user_id constraint.
        behavior = LearningBehavior.query.filter_by(user_id=user.id).first()
        if behavior is None:
            behavior = LearningBehavior(user_id=user.id)
            db.session.add(behavior)
        behavior.preferred_style = teaching_style
        db.session.add(UserProfile(user_id=user.id, full_name=full_name[:120], date_of_birth=date_of_birth, grade=grade, teaching_style=teaching_style, desired_plan=desired_plan, email_verified=True))
        db.session.commit()
        login_user(user)
        return jsonify({
            "success": True,
            "redirect": url_for("dashboard.home"),
        })

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        identifier = data.get("identifier", "").strip()
        password = data.get("password", "")
        remember = bool(data.get("remember", False))

        user = User.query.filter(
            (User.email == identifier.lower()) | (User.username == identifier)
        ).first()

        if not user or not user.check_password(password):
            if request.is_json:
                return jsonify({"success": False, "errors": ["Invalid credentials."]}), 401
            flash("Invalid email/username or password.", "error")
            return render_template("auth/login.html")
        if user.is_blocked:
            if request.is_json:
                return jsonify({"success": False, "errors": ["This account is currently unavailable. Contact support for help."]}), 403
            flash("This account is currently unavailable. Contact support for help.", "error")
            return render_template("auth/login.html"), 403

        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)

        next_page = request.args.get("next")
        if request.is_json:
            return jsonify({"success": True, "redirect": next_page or url_for("dashboard.home")})
        return redirect(next_page or url_for("dashboard.home"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index", logged_out="1"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        changed = False

        # Preserve any existing single-provider key under its current provider
        # before changing the selected provider.
        current_user.migrate_ai_api_keys()

        if data.get("ai_provider"):
            current_user.ai_provider = data["ai_provider"]
            changed = True
        if data.get("ai_model"):
            current_user.ai_model = data["ai_model"]
            changed = True
        if data.get("api_key"):
            current_user.set_ai_api_key(current_user.ai_provider, data["api_key"])
            changed = True
        if data.get("theme") in ("light", "dark"):
            current_user.theme = data["theme"]
            changed = True

        if changed:
            db.session.commit()
            if request.is_json:
                return jsonify({"success": True, "message": "Settings saved!"})
            flash("Settings updated.", "success")
        elif request.is_json:
            return jsonify({"success": True, "message": "Settings are already up to date."})

    from flask import current_app
    providers = current_app.config["AI_PROVIDERS"]
    return render_template("auth/settings.html", providers=providers)
