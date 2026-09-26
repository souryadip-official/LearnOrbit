"""
LearnOrbit Database Models
"""

from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"
    _AI_KEY_STORE_FORMAT = "learnorbit-provider-keys-v1"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    plan = db.Column(db.String(16), default="free")  # free | pro | team
    theme = db.Column(db.String(8), default="light")  # light | dark
    accent_theme = db.Column(db.String(24), default="garden")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # AI provider settings (stored per user)
    ai_provider = db.Column(db.String(32), default="openai")
    ai_model = db.Column(db.String(128), default="gpt-4o-mini")
    ai_api_key_enc = db.Column(db.Text)  # encrypted in production; plaintext for demo

    def migrate_ai_api_keys(self):
        """Wrap a legacy single key in a provider-key map without losing it."""
        raw = self.ai_api_key_enc
        if not raw:
            return
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            stored = None
        if isinstance(stored, dict) and stored.get("format") == self._AI_KEY_STORE_FORMAT:
            return
        self.ai_api_key_enc = json.dumps({
            "format": self._AI_KEY_STORE_FORMAT,
            "keys": {self.ai_provider: raw},
        })

    def get_ai_api_key(self, provider=None):
        """Get this user's key for a provider, including legacy single-key data."""
        provider = provider or self.ai_provider
        raw = self.ai_api_key_enc
        if not raw:
            return None
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            stored = None
        if isinstance(stored, dict) and stored.get("format") == self._AI_KEY_STORE_FORMAT:
            return stored.get("keys", {}).get(provider)
        return raw if provider == self.ai_provider else None

    def set_ai_api_key(self, provider, api_key):
        """Save one provider's key while preserving all other provider keys."""
        self.migrate_ai_api_keys()
        stored = json.loads(self.ai_api_key_enc) if self.ai_api_key_enc else {
            "format": self._AI_KEY_STORE_FORMAT, "keys": {}
        }
        stored.setdefault("keys", {})[provider] = api_key
        self.ai_api_key_enc = json.dumps(stored)

    # Relationships
    sessions = db.relationship("LearningSession", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    mastery_records = db.relationship("TopicMastery", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def plan_label(self):
        return {"free": "Explorer", "pro": "Scholar", "team": "Academy"}.get(self.plan, "Explorer")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "plan": self.plan,
            "theme": self.theme,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Learning Session
# ---------------------------------------------------------------------------

class LearningSession(db.Model):
    __tablename__ = "learning_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    topic = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(32), default="active")  # active | completed | abandoned
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)

    # Learning analytics
    messages_count = db.Column(db.Integer, default=0)
    quiz_score = db.Column(db.Float)
    mastery_score = db.Column(db.Float, default=0.0)
    difficulty_level = db.Column(db.String(16), default="beginner")  # beginner | intermediate | advanced

    # Stored conversation (JSON array of {role, content})
    conversation_json = db.Column(db.Text, default="[]")

    # Misconceptions detected
    misconceptions_json = db.Column(db.Text, default="[]")

    # Generated notes (markdown)
    notes_md = db.Column(db.Text)

    # Relationships
    quiz_attempts = db.relationship("QuizAttempt", backref="session", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def conversation(self):
        return json.loads(self.conversation_json or "[]")

    @conversation.setter
    def conversation(self, value):
        self.conversation_json = json.dumps(value)

    @property
    def misconceptions(self):
        return json.loads(self.misconceptions_json or "[]")

    @misconceptions.setter
    def misconceptions(self, value):
        self.misconceptions_json = json.dumps(value)

    def add_message(self, role, content):
        conv = self.conversation
        conv.append({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
        self.conversation = conv
        self.messages_count = len(conv)

    def to_dict(self):
        return {
            "id": self.id,
            "topic": self.topic,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "messages_count": self.messages_count,
            "quiz_score": self.quiz_score,
            "mastery_score": self.mastery_score,
            "difficulty_level": self.difficulty_level,
            "misconceptions": self.misconceptions,
        }


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------

class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("learning_sessions.id"), nullable=False)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)
    score = db.Column(db.Float)
    total_questions = db.Column(db.Integer)
    correct_answers = db.Column(db.Integer)

    # JSON: list of {question, options, correct, user_answer, explanation}
    questions_json = db.Column(db.Text, default="[]")

    @property
    def questions(self):
        return json.loads(self.questions_json or "[]")

    @questions.setter
    def questions(self, value):
        self.questions_json = json.dumps(value)


# ---------------------------------------------------------------------------
# Topic Mastery
# ---------------------------------------------------------------------------

class TopicMastery(db.Model):
    __tablename__ = "topic_mastery"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    topic = db.Column(db.String(256), nullable=False)
    topic_slug = db.Column(db.String(256), nullable=False, index=True)

    # Sub-scores 0–100
    understanding = db.Column(db.Float, default=0.0)
    application = db.Column(db.Float, default=0.0)
    problem_solving = db.Column(db.Float, default=0.0)
    retention = db.Column(db.Float, default=0.0)

    overall = db.Column(db.Float, default=0.0)
    sessions_count = db.Column(db.Integer, default=0)
    last_studied = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "topic_slug", name="_user_topic_uc"),)

    def recalculate_overall(self):
        self.overall = round(
            (self.understanding * 0.35 + self.application * 0.25
             + self.problem_solving * 0.25 + self.retention * 0.15), 1
        )

    def to_dict(self):
        return {
            "topic": self.topic,
            "understanding": self.understanding,
            "application": self.application,
            "problem_solving": self.problem_solving,
            "retention": self.retention,
            "overall": self.overall,
            "sessions_count": self.sessions_count,
            "last_studied": self.last_studied.isoformat() if self.last_studied else None,
        }


# ---------------------------------------------------------------------------
# Learning Behavior Analytics
# ---------------------------------------------------------------------------

class LearningBehavior(db.Model):
    __tablename__ = "learning_behavior"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    # Aggregated style inference
    preferred_style = db.Column(db.String(32), default="balanced")  # visual | analytical | narrative | balanced
    avg_session_duration_mins = db.Column(db.Float, default=0.0)
    avg_questions_per_session = db.Column(db.Float, default=0.0)
    total_sessions = db.Column(db.Integer, default=0)
    total_topics = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=0)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

    # JSON: {topics: [], weak_areas: [], strong_areas: []}
    profile_json = db.Column(db.Text, default="{}")

    @property
    def profile(self):
        return json.loads(self.profile_json or "{}")

    @profile.setter
    def profile(self, value):
        self.profile_json = json.dumps(value)

    def to_dict(self):
        return {
            "preferred_style": self.preferred_style,
            "avg_session_duration_mins": self.avg_session_duration_mins,
            "total_sessions": self.total_sessions,
            "total_topics": self.total_topics,
            "streak_days": self.streak_days,
            "profile": self.profile,
        }


class UserProfile(db.Model):
    __tablename__ = "user_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), default="")
    date_of_birth = db.Column(db.String(10), default="")
    grade = db.Column(db.String(40), default="")
    teaching_style = db.Column(db.String(32), default="balanced")
    desired_plan = db.Column(db.String(16), default="free")
    email_verified = db.Column(db.Boolean, default=True)
    avatar = db.Column(db.String(64), default="orbit-1")
    picture_path = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionDocument(db.Model):
    __tablename__ = "session_documents"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("learning_sessions.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    extracted_text = db.Column(db.Text, nullable=False)
    embedding_provider = db.Column(db.String(32))
    embeddings_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GameUsage(db.Model):
    __tablename__ = "game_usage"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    ended_at = db.Column(db.DateTime)


class GameScore(db.Model):
    __tablename__ = "game_scores"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    game_id = db.Column(db.String(32), nullable=False)
    score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CalendarEvent(db.Model):
    __tablename__ = "calendar_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    details = db.Column(db.Text, default="")
    starts_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AttendanceStamp(db.Model):
    __tablename__ = "attendance_stamps"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    attended_on = db.Column(db.Date, nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("user_id", "attended_on", name="_user_attendance_day_uc"),)


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), default="active")
    current_period_start = db.Column(db.DateTime, default=datetime.utcnow)
    current_period_end = db.Column(db.DateTime, nullable=False)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    scheduled_plan = db.Column(db.String(16))


class PaymentRecord(db.Model):
    __tablename__ = "payment_records"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(16), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(16), default="demo")
    reference = db.Column(db.String(40), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CodeSnippet(db.Model):
    __tablename__ = "code_snippets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(120), default="Untitled")
    language = db.Column(db.String(24), default="python")
    source_code = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailOTP(db.Model):
    __tablename__ = "email_otps"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(16), nullable=False)
    code_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0)
