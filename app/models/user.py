"""User model for Week 2 authentication (registration starts in step 2)."""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    subjects = db.relationship('Subject', back_populates='owner', lazy='select')
    tasks = db.relationship('Task', back_populates='owner', lazy='select')
    exams = db.relationship('Exam', back_populates='owner', lazy='select')
    study_sessions = db.relationship('StudySession', back_populates='owner', lazy='select')

    def set_password(self, password):
        """Store a salted one-way hash, never the plaintext password."""
        if not isinstance(password, str) or not password:
            raise ValueError('Паролата не може да бъде празна.')
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User id={self.id} username={self.username!r}>'
