"""User-owned study sessions for the weekly timetable (Week 3 / Step 2)."""
from datetime import datetime, timezone
from app import db


class StudySession(db.Model):
    __tablename__ = 'study_sessions'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    session_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='planned')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False, index=True)
    owner = db.relationship('User', back_populates='study_sessions')
    subject = db.relationship('Subject', back_populates='study_sessions')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        db.CheckConstraint('start_time < end_time', name='ck_study_sessions_time_order'),
        db.CheckConstraint("status IN ('planned', 'completed', 'cancelled')", name='ck_study_sessions_status'),
    )
