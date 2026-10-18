"""Task model: each task belongs to one user; a subject is optional."""
from datetime import datetime, timezone
from app import db


class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(10), nullable=False, default='medium')
    status = db.Column(db.String(15), nullable=False, default='pending')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True, index=True)
    owner = db.relationship('User', back_populates='tasks')
    subject = db.relationship('Subject', back_populates='tasks')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        db.CheckConstraint("priority IN ('low', 'medium', 'high')", name='ck_tasks_priority'),
        db.CheckConstraint("status IN ('pending', 'in_progress', 'completed')", name='ck_tasks_status'),
    )
