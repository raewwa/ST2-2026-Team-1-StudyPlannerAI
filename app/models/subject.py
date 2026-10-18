"""Subject database model; INSERT and filtered SELECT are implemented in week 1."""
from datetime import datetime, timezone
from app import db


class Subject(db.Model):
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    # Nullable for Week 1 legacy records; scoped ownership comes in Week 2 step 2.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    owner = db.relationship('User', back_populates='subjects')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Subject {self.name!r}>'
