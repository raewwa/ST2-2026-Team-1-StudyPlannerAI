"""Subject repository: owner-scoped subject reads and writes."""
from app.models.subject import Subject
from .base import OwnedRepository


class SubjectRepository(OwnedRepository):
    model = Subject

    def ordered(self):
        return self.query().order_by(Subject.name).all()

    def count(self):
        return self.query().count()
