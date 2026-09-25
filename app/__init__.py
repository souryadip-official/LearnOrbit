"""
LearnOrbit Application Factory
"""

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
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

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        # AJAX callers expect JSON; Flask-WTF's default HTML 400 obscures the cause.
        if request.path.startswith(("/tutor/", "/api/", "/auth/")):
            return jsonify({"error": "Security token expired or missing. Refresh the page and try again."}), 400
        return "Security token expired or missing. Please refresh and try again.", 400

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue your learning journey! 🚀"
    login_manager.login_message_category = "info"

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.tutor import tutor_bp
    from .routes.quiz import quiz_bp
    from .routes.notes import notes_bp
    from .routes.games import games_bp
    from .routes.api import api_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(tutor_bp, url_prefix="/tutor")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(games_bp, url_prefix="/games")
    app.register_blueprint(api_bp, url_prefix="/api")

    # Landing page route
    from flask import render_template
    @app.route("/")
    def index():
        return render_template("landing.html")

    # Create tables
    with app.app_context():
        db.create_all()

    return app
