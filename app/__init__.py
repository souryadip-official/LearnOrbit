"""
LearnOrbit Application Factory
"""

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import inspect, text
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    # Load config
    from .config import config
    cfg = config.get(config_name or os.getenv("FLASK_ENV", "development"))
    app.config.from_object(cfg)

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    @app.context_processor
    def inject_user_profile():
        from flask_login import current_user
        if current_user.is_authenticated:
            from .models import UserProfile
            return {"user_profile": UserProfile.query.filter_by(user_id=current_user.id).first()}
        return {"user_profile": None}

    @app.before_request
    def reconcile_subscription_cycle():
        from flask_login import current_user
        if not current_user.is_authenticated:
            return
        from .models import Subscription
        from datetime import datetime, timedelta
        row = Subscription.query.filter_by(user_id=current_user.id, status="active").order_by(Subscription.id.desc()).first()
        if not row or row.current_period_end > datetime.utcnow():
            return
        if row.cancel_at_period_end:
            row.status = "cancelled"
            current_user.plan = "free"
        elif row.scheduled_plan:
            row.plan = row.scheduled_plan
            row.scheduled_plan = None
            row.current_period_start = row.current_period_end
            row.current_period_end = row.current_period_end + timedelta(days=30)
            current_user.plan = row.plan
        else:
            row.current_period_start = row.current_period_end
            row.current_period_end = row.current_period_end + timedelta(days=30)
        db.session.commit()

    @app.before_request
    def record_daily_attendance():
        from flask_login import current_user
        from datetime import date
        if not current_user.is_authenticated or request.endpoint == "static":
            return
        from .models import AttendanceStamp
        if not AttendanceStamp.query.filter_by(user_id=current_user.id, attended_on=date.today()).first():
            db.session.add(AttendanceStamp(user_id=current_user.id, attended_on=date.today()))
            db.session.commit()

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        # AJAX callers expect JSON; Flask-WTF's default HTML 400 obscures the cause.
        if request.path.startswith(("/tutor/", "/api/", "/auth/")):
            return jsonify({"error": "Security token expired or missing. Refresh the page and try again."}), 400
        return "Security token expired or missing. Please refresh and try again.", 400

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue your learning journey."
    login_manager.login_message_category = "info"

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.tutor import tutor_bp
    from .routes.quiz import quiz_bp
    from .routes.notes import notes_bp
    from .routes.games import games_bp
    from .routes.api import api_bp
    from .routes.features import features_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(tutor_bp, url_prefix="/tutor")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(games_bp, url_prefix="/games")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(features_bp, url_prefix="/features")

    # Landing page route
    from flask import render_template
    @app.route("/")
    def index():
        return render_template("landing.html")

    # Create tables
    with app.app_context():
        db.create_all()
        _migrate_legacy_schema()

    return app


def _migrate_legacy_schema():
    """Add known feature columns missing from databases created by older versions.

    ``create_all`` creates new tables, but deliberately does not change tables
    that already exist. This migration is additive and idempotent, preserving
    profile rows while supplying defaults for newly introduced fields.
    """
    from .models import SessionDocument, UserProfile, User

    # SQL defaults are needed for legacy rows; ORM defaults only run on inserts.
    migrations = {
        "users": (User, {"accent_theme": "VARCHAR(24) DEFAULT 'garden'"}),
        "user_profiles": (UserProfile, {
            "desired_plan": "VARCHAR(16) DEFAULT 'free'",
            "email_verified": "BOOLEAN DEFAULT 1",
            "avatar": "VARCHAR(64) DEFAULT 'orbit-1'",
            "picture_path": "VARCHAR(255)",
            "updated_at": "DATETIME",
        }),
        "session_documents": (SessionDocument, {
            "storage_path": "VARCHAR(500) NOT NULL DEFAULT ''",
            "embedding_provider": "VARCHAR(32)",
            "embeddings_json": "TEXT",
            "created_at": "DATETIME",
        }),
    }
    inspector = inspect(db.engine)
    with db.engine.begin() as connection:
        for table_name, (model, additions) in migrations.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            model_columns = {column.name for column in model.__table__.columns}
            missing = (model_columns & additions.keys()) - existing
            for column_name in additions:
                if column_name in missing:
                    connection.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {additions[column_name]}"
                    ))
