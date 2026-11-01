"""Task repository: owner-scoped CRUD and filters."""
from app.models.task import Task
from sqlalchemy import case
from .base import OwnedRepository


class TaskRepository(OwnedRepository):
    model = Task

    def filtered(self, filters=None):
        query = self.query()
        for key, value in (filters or {}).items():
            if key in ('status', 'priority', 'subject_id') and value:
                query = query.filter(getattr(Task, key) == value)
        filters = filters or {}
        if filters.get('search'):
            escaped = filters['search'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            query = query.filter(Task.title.ilike(f'%{escaped}%', escape='\\'))
        sort = filters.get('sort', 'newest')
        order = {
            'newest': (Task.id.desc(),), 'oldest': (Task.id.asc(),),
            'due_asc': (Task.due_date.is_(None), Task.due_date.asc(), Task.id.desc()),
            'due_desc': (Task.due_date.is_(None), Task.due_date.desc(), Task.id.desc()),
            'priority': (case((Task.priority == 'high', 0), (Task.priority == 'medium', 1), else_=2), Task.id.desc()),
        }
        return query.order_by(*order.get(sort, order['newest'])).all()
