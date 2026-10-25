"""Exam entity with database-level validation (Week 3 / Step 1)."""
from datetime import datetime, timezone
from app import db

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    exam_date = db.Column(db.Date, nullable=False)
    exam_time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(160))
    status = db.Column(db.String(20), nullable=False, default='upcoming')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False, index=True)
    owner = db.relationship('User', back_populates='exams')
    subject = db.relationship('Subject', back_populates='exams')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.CheckConstraint("status IN ('upcoming', 'completed', 'cancelled')", name='ck_exams_status'),)
