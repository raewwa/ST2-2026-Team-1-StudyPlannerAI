import pytest
from app import create_app, db


def register_test_user(client):
    import re
    page = client.get('/register')
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    assert client.post('/register', data={'csrf_token': token, 'username': 'smoke_user',
        'email': 'smoke@example.com', 'password': 'password123',
        'confirm_password': 'password123'}).status_code == 302


@pytest.mark.parametrize('route', ['/login', '/register'])
def test_pages_load(client, route):
    response = client.get(route)
    assert response.status_code == 200
    assert b'AI Study Planner' in response.data


def test_subjects_table_created(client):
    from sqlalchemy import inspect
    from app import db
    with client.application.app_context():
        assert 'subjects' in inspect(db.engine).get_table_names()


def test_subject_insert_and_dashboard_count(client):
    register_test_user(client)
    page = client.get('/subjects')
    import re
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    response = client.post('/subjects', data={
        'csrf_token': token, 'name': '  Математика  ', 'semester': '3',
        'description': 'Линейна алгебра',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert 'Математика'.encode() in response.data
    with client.application.app_context():
        from app.models.subject import Subject
        assert Subject.query.count() == 1
        assert Subject.query.first().name == 'Математика'
    assert 'Предмети' in client.get('/').get_data(as_text=True)
    assert 'Математика' in client.get('/subjects').get_data(as_text=True)


def test_subject_validation_and_csrf(client):
    register_test_user(client)
    assert client.post('/subjects', data={'name': 'X'}).status_code == 400
    page = client.get('/subjects')
    import re
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    for data in ({'name': '', 'semester': '2'}, {'name': 'Test', 'semester': '15'},
                 {'name': 'A' * 121}, {'name': 'Test', 'description': 'x' * 1001}):
        response = client.post('/subjects', data={'csrf_token': token, **data})
        assert response.status_code == 422
    with client.application.app_context():
        from app.models.subject import Subject
        assert Subject.query.count() == 0


def test_dashboard_uses_bootstrap_icons_not_emoji(client):
    register_test_user(client)
    response = client.get('/')
    assert b'bootstrap-icons' in response.data
    assert b'bi bi-book' in response.data


def test_tasks_requires_login(client):
    response = client.get('/tasks')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
