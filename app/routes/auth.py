"""
LearnOrbit Authentication Routes
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, csrf
from app.models import User, LearningBehavior, UserProfile
from app.models import EmailOTP
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os, secrets, smtplib
from email.message import EmailMessage
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


def _send_otp(user, purpose):
    host = os.getenv("SMTP_HOST")
    if not host and not current_app.debug:
        raise RuntimeError("SMTP is required for email verification outside development.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    EmailOTP.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.add(EmailOTP(user_id=user.id, purpose=purpose, code_hash=generate_password_hash(code), expires_at=datetime.utcnow()+timedelta(minutes=10)))
    db.session.commit()
    if not host:
        current_app.logger.warning("Development OTP for %s (%s): %s", user.email, purpose, code)
        session["otp_pending_user"] = user.id; session["otp_pending_purpose"] = purpose
        return True
    message = EmailMessage(); message["Subject"] = "Your LearnOrbit sign-in code"; message["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")); message["To"] = user.email
    message.set_content(f"Your LearnOrbit verification code is {code}. It expires in 10 minutes. If you did not request this, ignore this message.")
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            if os.getenv("SMTP_USER"): server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            server.send_message(message)
        session["otp_pending_user"] = user.id; session["otp_pending_purpose"] = purpose
        return True
    except Exception:
        EmailOTP.query.filter_by(user_id=user.id).delete(synchronize_session=False); db.session.commit()
        raise


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

        if not os.getenv("SMTP_HOST") and not current_app.debug:
            return jsonify({"success": False, "errors": ["Email verification is temporarily unavailable. Please try again later."]}), 503

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
        db.session.add(UserProfile(user_id=user.id, full_name=full_name[:120], date_of_birth=date_of_birth, grade=grade, teaching_style=teaching_style, desired_plan=desired_plan, email_verified=False))
        db.session.commit()
        try:
            _send_otp(user, "register")
            return jsonify({"success": True, "otp_required": True, "message": "Enter your six-digit email verification code. In local development, the code is printed in the server terminal."})
        except Exception:
            return jsonify({"success": False, "errors": ["Could not send verification code. Configure SMTP and try again."]}), 503

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

        try:
            _send_otp(user, "login")
            session["otp_remember"] = remember
            return jsonify({"success": True, "otp_required": True, "message": "A six-digit sign-in code was sent to your email. In local development, check the server terminal."})
        except Exception:
            return jsonify({"success": False, "errors": ["Could not send the verification email. Check SMTP settings and try again."]}), 503
        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)

        next_page = request.args.get("next")
        if request.is_json:
            return jsonify({"success": True, "redirect": next_page or url_for("dashboard.home")})
        return redirect(next_page or url_for("dashboard.home"))

    return render_template("auth/login.html")


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    user_id = session.get("otp_pending_user"); purpose = session.get("otp_pending_purpose")
    row = EmailOTP.query.filter_by(user_id=user_id, purpose=purpose).first() if user_id and purpose else None
    if not row or row.expires_at < datetime.utcnow() or row.attempts >= 5:
        session.pop("otp_pending_user", None); session.pop("otp_pending_purpose", None)
        return jsonify({"error": "Code expired or attempts exceeded. Sign in again for a new code."}), 400
    row.attempts += 1
    if not check_password_hash(row.code_hash, str(data.get("code", ""))):
        db.session.commit(); return jsonify({"error": "That code does not match."}), 400
    user = User.query.get(user_id)
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if profile: profile.email_verified = True
    user.last_login = datetime.utcnow(); db.session.delete(row); db.session.commit()
    completed_purpose = purpose
    remember = bool(session.pop("otp_remember", False)); session.pop("otp_pending_user", None); session.pop("otp_pending_purpose", None)
    if completed_purpose == "register":
        return jsonify({"success": True, "registered": True, "redirect": url_for("auth.login"), "message": "Email verified. Please log in to start learning."})
    login_user(user, remember=remember)
    return jsonify({"success": True, "redirect": url_for("dashboard.home")})


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    user_id = session.get("otp_pending_user"); purpose = session.get("otp_pending_purpose")
    user = User.query.get(user_id) if user_id and purpose else None
    if not user or (not os.getenv("SMTP_HOST") and not current_app.debug):
        return jsonify({"error": "Start sign-in again to request a new code."}), 400
    try:
        _send_otp(user, purpose)
        return jsonify({"success": True, "message": "A new code has been emailed. The previous code has expired."})
    except Exception:
        return jsonify({"error": "Could not send another code. Check SMTP settings and try again."}), 503


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("See you next time! Keep learning.", "info")
    return redirect(url_for("index"))


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
