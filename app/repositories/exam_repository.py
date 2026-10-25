"""Exam repository: owner-scoped CRUD and chronological list."""
from app.models.exam import Exam
from .base import OwnedRepository


class ExamRepository(OwnedRepository):
    model = Exam

    def ordered(self):
        return self.query().order_by(Exam.exam_date, Exam.exam_time).all()
