"""Week 2 final: protected routes, scoped data, dashboard and profile card."""
import re
import pytest
from app import create_app, db
from app.models.subject import Subject
from app.models.task import Task


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'step5-secret',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "step5.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def token(client, path):
    return re.search(rb'name="csrf_token" value="([^"]+)"', client.get(path).data).group(1).decode()


def register(client, name):
    return client.post('/register', data={'csrf_token': token(client, '/register'),
        'username': name, 'email': f'{name}@example.com', 'password': 'password123',
        'confirm_password': 'password123'})


@pytest.mark.parametrize('path', ['/', '/subjects', '/tasks', '/exams', '/schedule'])
def test_all_workspace_pages_require_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_public_pages_and_profile_card(client):
    assert client.get('/login').status_code == 200
    assert client.get('/register').status_code == 200
    assert register(client, 'maria').status_code == 302
    html = client.get('/').get_data(as_text=True)
    assert 'profile-card' in html
    assert 'maria@example.com' in html
    assert 'Изход от профила' in html
    assert 'Седмица 2 · Завършена' in html


def test_dashboard_counts_are_user_scoped(client):
    register(client, 'student1')
    assert client.post('/subjects', data={'csrf_token': token(client, '/subjects'),
        'name': 'Математика'}).status_code == 302
    assert client.post('/tasks', data={'csrf_token': token(client, '/tasks'),
        'title': 'Домашно'}).status_code == 302
    html = client.get('/').get_data(as_text=True)
    assert 'Общо задачи:' in html
    assert 'За изпълнение: 1' in html
    client.post('/logout', data={'csrf_token': token(client, '/')})
    assert register(client, 'student2').status_code == 302
    html = client.get('/').get_data(as_text=True)
    assert 'За изпълнение: 0' in html
    assert 'Добавени предмети: <strong>0</strong>' in html
    with client.application.app_context():
        assert Subject.query.count() == 1
        assert Task.query.count() == 1


def test_subjects_post_requires_login_and_csrf(client):
    assert client.post('/subjects', data={'name': 'Чужд'}).status_code == 302
    register(client, 'student3')
    assert client.post('/subjects', data={'name': 'Без токен'}).status_code == 400
