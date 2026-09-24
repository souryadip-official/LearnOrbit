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

    # PDF export
    EXPORT_DIR = os.path.join(BASE_DIR, "exports")

    # Pricing tiers
    PRICING = {
        "free": {
            "name": "Explorer",
            "price": 0,
            "sessions_per_day": 3,
            "quizzes_per_session": 1,
            "notes_export": False,
            "games_access": True,
            "split_screen": False,
        },
        "pro": {
            "name": "Scholar",
            "price": 9.99,
            "sessions_per_day": -1,  # unlimited
            "quizzes_per_session": -1,
            "notes_export": True,
            "games_access": True,
            "split_screen": True,
        },
        "team": {
            "name": "Academy",
            "price": 24.99,
            "sessions_per_day": -1,
            "quizzes_per_session": -1,
            "notes_export": True,
            "games_access": True,
            "split_screen": True,
        },
    }

    # Supported AI providers
    AI_PROVIDERS = {
        "openai": {
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini"],
            "base_url": "https://api.openai.com/v1",
        },
        "google": {
            "name": "Google Gemini",
            "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
        },
        "anthropic": {
            "name": "Anthropic Claude",
            "models": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
            "base_url": "https://api.anthropic.com/v1",
        },
        "xai": {
            "name": "xAI Grok",
            "models": ["grok-3", "grok-3-mini", "grok-2"],
            "base_url": "https://api.x.ai/v1",
        },
        "huggingface": {
            "name": "Hugging Face",
            "models": [
                "meta-llama/Meta-Llama-3.1-70B-Instruct",
                "meta-llama/Meta-Llama-3.1-8B-Instruct",
                "mistralai/Mixtral-8x7B-Instruct-v0.1",
                "mistralai/Mistral-7B-Instruct-v0.3",
                "google/gemma-2-27b-it",
                "google/gemma-2-9b-it",
                "Qwen/Qwen2.5-72B-Instruct",
                "Qwen/Qwen2.5-7B-Instruct",
                "microsoft/Phi-3.5-mini-instruct",
                "tiiuae/falcon-7b-instruct",
            ],
            "base_url": "https://api-inference.huggingface.co/models",
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
