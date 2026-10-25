"""Task repository: owner-scoped CRUD and filters."""
from app.models.task import Task
from .base import OwnedRepository


class TaskRepository(OwnedRepository):
    model = Task

    def filtered(self, filters=None):
        query = self.query()
        for key, value in (filters or {}).items():
            if key in ('status', 'priority', 'subject_id') and value:
                query = query.filter(getattr(Task, key) == value)
        return query.order_by(Task.id.desc()).all()
