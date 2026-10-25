"""Study session repository: owner-scoped CRUD, weekly list and overlap checks."""
from app.models.study_session import StudySession
from .base import OwnedRepository


class StudySessionRepository(OwnedRepository):
    model = StudySession

    def in_week(self, monday, sunday):
        return self.query().filter(
            StudySession.session_date >= monday,
            StudySession.session_date <= sunday,
        ).order_by(StudySession.session_date, StudySession.start_time).all()

    def overlaps(self, session_date, start_time, end_time, exclude_id=None):
        query = self.query().filter(
            StudySession.session_date == session_date,
            StudySession.status != 'cancelled',
            StudySession.start_time < end_time,
            StudySession.end_time > start_time,
        )
        if exclude_id is not None:
            query = query.filter(StudySession.id != exclude_id)
        return query.first() is not None
