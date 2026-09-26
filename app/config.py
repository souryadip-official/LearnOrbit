"""
LearnOrbit Configuration
"""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "learnorbit-secret-change-in-prod-2024")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    WTF_CSRF_ENABLED = True

    # Pricing tiers
    PRICING = {
        "free": {
            "name": "Explorer",
            "price": 0,
            "sessions_per_day": 3,
            "quizzes_per_session": 1,
            "games_access": True,
            "split_screen": False,
        },
        "pro": {
            "name": "Scholar",
            "price": 9.99,
            "sessions_per_day": -1,  # unlimited
            "quizzes_per_session": -1,
            "games_access": True,
            "split_screen": True,
        },
        "team": {
            "name": "Academy",
            "price": 24.99,
            "sessions_per_day": -1,
            "quizzes_per_session": -1,
            "games_access": True,
            "split_screen": True,
        },
    }

    # Supported AI providers
    AI_PROVIDERS = {
        "openai": {
            "name": "OpenAI",
            "models": ["gpt-5.5", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini"],
            "base_url": "https://api.openai.com/v1",
        },
        "google": {
            "name": "Google Gemini",
            "models": ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-pro-preview"],
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
        },
        "anthropic": {
            "name": "Anthropic Claude",
            "models": ["claude-fable-5.1", "claude-sonnet-4.6", "claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
            "base_url": "https://api.anthropic.com/v1",
        },
        "xai": {
            "name": "xAI Grok",
            "models": ["grok-4.7", "grok-4.6", "grok-4.5", "grok-4.3", "grok-3", "grok-3-mini", "grok-2"],
            "base_url": "https://api.x.ai/v1",
        },
        "huggingface": {
            "name": "Hugging Face",
            # Fallback list; the settings page loads the current catalog from
            # the Inference Providers router when it is available.
            "models": ["openai/gpt-oss-120b"],
            "base_url": "https://router.huggingface.co/v1",
        },
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'learnorbit_dev.db')}"
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'learnorbit.db')}")


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
