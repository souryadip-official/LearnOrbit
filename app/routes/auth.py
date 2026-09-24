"""
LearnOrbit Authentication Routes
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db, csrf
from app.models import User, LearningBehavior
from datetime import datetime

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
@csrf.exempt
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        errors = []
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if not email or "@" not in email:
            errors.append("Valid email required.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters.")
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
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Create learning behavior record
        behavior = LearningBehavior(user_id=user.id)
        db.session.add(behavior)
        db.session.commit()

        login_user(user, remember=True)
        if request.is_json:
            return jsonify({"success": True, "redirect": url_for("dashboard.home")})
        flash("Welcome to LearnOrbit! 🚀 Your learning journey begins now!", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf.exempt
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
    flash("See you next time! Keep learning! 📚", "info")
    return redirect(url_for("index"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        changed = False

        if data.get("ai_provider"):
            current_user.ai_provider = data["ai_provider"]
            changed = True
        if data.get("ai_model"):
            current_user.ai_model = data["ai_model"]
            changed = True
        if data.get("api_key"):
            current_user.ai_api_key_enc = data["api_key"]
            changed = True
        if data.get("theme") in ("light", "dark"):
            current_user.theme = data["theme"]
            changed = True

        if changed:
            db.session.commit()
            if request.is_json:
                return jsonify({"success": True, "message": "Settings saved!"})
            flash("Settings updated! ✅", "success")

    from flask import current_app
    providers = current_app.config["AI_PROVIDERS"]
    return render_template("auth/settings.html", providers=providers)
