"""
LearnOrbit — Database initialisation helper
Run: python init_db.py
"""

from app import create_app, db
from app.models import User, LearningSession, QuizAttempt, TopicMastery, LearningBehavior

app = create_app()

with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully.")
    print("   Tables:", [t.__tablename__ for t in [User, LearningSession, QuizAttempt, TopicMastery, LearningBehavior]])
