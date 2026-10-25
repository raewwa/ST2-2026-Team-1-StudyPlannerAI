"""Repository design pattern: isolate SQLAlchemy persistence from HTTP controllers.

Every owned repository requires an explicit user ID. All object lookups and
queries are scoped to it, including update/delete targets (404 if foreign).
"""
from app import db


class OwnedRepository:
    model = None

    def __init__(self, user_id):
        if not isinstance(user_id, int) or user_id < 1:
            raise ValueError('A valid authenticated user id is required')
        self.user_id = user_id

    def query(self):
        return db.session.query(self.model).filter(self.model.user_id == self.user_id)

    def get_or_404(self, item_id):
        return self.query().filter(self.model.id == item_id).first_or_404()

    def add(self, **values):
        # user_id is always set by the repository, never trusted from the form.
        values.pop('user_id', None)
        item = self.model(**values, user_id=self.user_id)
        db.session.add(item)
        db.session.commit()
        return item

    def update(self, item, **values):
        if item.user_id != self.user_id:
            raise ValueError('Cannot update an item owned by another user')
        values.pop('user_id', None)
        for field, value in values.items():
            setattr(item, field, value)
        db.session.commit()
        return item

    def delete(self, item):
        if item.user_id != self.user_id:
            raise ValueError('Cannot delete an item owned by another user')
        db.session.delete(item)
        db.session.commit()

    def exists(self, item_id):
        return self.query().filter(self.model.id == item_id).first() is not None
