"""Week 2 step 4: CRUD, filters, CSRF and owner isolation."""
import re
import pytest
from app import create_app, db
from app.models.task import Task


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'step4',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "step4.db"}'})
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def csrf(client, path='/tasks'):
    return re.search(rb'name="csrf_token" value="([^"]+)"', client.get(path).data).group(1).decode()


def register(client, name):
    return client.post('/register', data={'csrf_token': csrf(client, '/register'),
        'username': name, 'email': name + '@example.com',
        'password': 'password123', 'confirm_password': 'password123'})


def create_task(client, title='Моята задача', **fields):
    return client.post('/tasks', data={'csrf_token': csrf(client), 'title': title, **fields})


def test_update_toggle_delete(client):
    register(client, 'student_a')
    assert create_task(client).status_code == 302
    with client.application.app_context():
        task_id = Task.query.one().id
    path = f'/tasks/{task_id}'
    assert client.get(path + '/edit').status_code == 200
    assert client.post(path + '/edit', data={'title': 'Невалиден CSRF'}).status_code == 400
    assert client.post(path + '/edit', data={'csrf_token': csrf(client, path + '/edit'),
        'title': 'Обновена', 'priority': 'high', 'status': 'in_progress'}).status_code == 302
    with client.application.app_context():
        assert Task.query.one().title == 'Обновена'
    assert client.post(path + '/toggle', data={'csrf_token': csrf(client)}).status_code == 302
    with client.application.app_context():
        assert Task.query.one().status == 'completed'
    assert client.post(path + '/toggle', data={'csrf_token': csrf(client)}).status_code == 302
    with client.application.app_context():
        assert Task.query.one().status == 'pending'
    assert client.post(path + '/delete', data={}).status_code == 400
    assert client.post(path + '/delete', data={'csrf_token': csrf(client)}).status_code == 302
    with client.application.app_context():
        assert Task.query.count() == 0


def test_filters_and_invalid_filter(client):
    register(client, 'student_b')
    create_task(client, 'Висок приоритет', priority='high', status='pending')
    create_task(client, 'Нисък приоритет', priority='low', status='completed')
    page = client.get('/tasks?priority=high&status=pending').get_data(as_text=True)
    assert 'Висок приоритет' in page and 'Нисък приоритет' not in page
    page = client.get('/tasks?priority=invalid').get_data(as_text=True)
    assert 'Невалиден приоритет.' in page
    assert 'Висок приоритет' not in page


def test_other_user_cannot_modify_task(client):
    register(client, 'student_c')
    create_task(client)
    with client.application.app_context():
        task_id = Task.query.one().id
    client.post('/logout', data={'csrf_token': csrf(client, '/')})
    register(client, 'student_d')
    path = f'/tasks/{task_id}'
    assert client.get(path + '/edit').status_code == 404
    for action in ('edit', 'delete', 'toggle'):
        assert client.post(path + '/' + action, data={'csrf_token': csrf(client)}).status_code == 404
    with client.application.app_context():
        assert Task.query.one().title == 'Моята задача'
