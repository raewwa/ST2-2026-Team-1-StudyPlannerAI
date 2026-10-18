"""Week 2 step 3: tasks Create/Read, validation, CSRF and ownership."""
import re
import pytest
from app import create_app, db
from app.models.task import Task
from app.models.subject import Subject


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'task-test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "tasks.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def csrf(client, path):
    response = client.get(path)
    return re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()


def register(client, name):
    return client.post('/register', data={'csrf_token': csrf(client, '/register'),
        'username': name, 'email': f'{name}@example.com', 'password': 'password123',
        'confirm_password': 'password123'})


def test_tasks_require_login_and_csrf(client):
    assert client.get('/tasks').status_code == 302
    assert register(client, 'student1').status_code == 302
    assert client.post('/tasks', data={'title': 'Unsafe'}).status_code == 400
    with client.application.app_context():
        assert Task.query.count() == 0


def test_create_read_and_owner_isolation(client):
    register(client, 'student1')
    client.post('/subjects', data={'csrf_token': csrf(client, '/subjects'), 'name': 'Математика'})
    with client.application.app_context():
        subject_id = Subject.query.filter_by(name='Математика').one().id
    result = client.post('/tasks', data={'csrf_token': csrf(client, '/tasks'), 'title': 'Реши задачи',
        'description': 'Глава 3', 'due_date': '2026-12-01', 'priority': 'high',
        'status': 'in_progress', 'subject_id': str(subject_id)})
    assert result.status_code == 302
    assert 'Реши задачи'.encode() in client.get('/tasks').data
    with client.application.app_context():
        task = Task.query.one()
        assert task.subject_id == subject_id and task.priority == 'high'
    client.post('/logout', data={'csrf_token': csrf(client, '/')})
    register(client, 'student2')
    assert 'Реши задачи'.encode() not in client.get('/tasks').data
    denied = client.post('/tasks', data={'csrf_token': csrf(client, '/tasks'),
        'title': 'Чужд предмет', 'subject_id': str(subject_id)})
    assert denied.status_code == 422
    with client.application.app_context():
        assert Task.query.count() == 1


def test_invalid_task_fields(client):
    register(client, 'student3')
    for payload in ({'title': ''}, {'title': 'x' * 161}, {'title': 'Ok', 'priority': 'invalid'},
                    {'title': 'Ok', 'status': 'invalid'}, {'title': 'Ok', 'due_date': '2026-99-99'},
                    {'title': 'Ok', 'subject_id': 'not-a-number'}):
        response = client.post('/tasks', data={'csrf_token': csrf(client, '/tasks'), **payload})
        assert response.status_code == 422
    with client.application.app_context():
        assert Task.query.count() == 0
