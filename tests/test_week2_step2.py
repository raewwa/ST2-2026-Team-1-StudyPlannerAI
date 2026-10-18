"""Week 2 step 2: registration, login, logout, privacy and footer."""
import re
import pytest
from app import create_app, db
from app.models.user import User


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "auth.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def token(client, path):
    page = client.get(path)
    return re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()


def register(client, username='ivan', email='ivan@example.com'):
    return client.post('/register', data={'csrf_token': token(client, '/register'),
        'username': username, 'email': email, 'password': 'password123',
        'confirm_password': 'password123'})


def test_registration_login_logout_and_footer(client):
    assert b'app-footer' in client.get('/login').data
    assert register(client).status_code == 302
    with client.application.app_context():
        user = User.query.one()
        assert user.check_password('password123')
        assert user.password_hash != 'password123'
    assert 'ivan'.encode() in client.get('/').data
    logout_token = token(client, '/')
    assert client.post('/logout', data={'csrf_token': logout_token}).status_code == 302
    assert client.get('/login').status_code == 200
    bad = client.post('/login', data={'csrf_token': token(client, '/login'),
        'email': 'ivan@example.com', 'password': 'wrong'})
    assert bad.status_code == 401
    ok = client.post('/login', data={'csrf_token': token(client, '/login'),
        'email': 'IVAN@example.com', 'password': 'password123'})
    assert ok.status_code == 302


def test_invalid_registration_and_csrf(client):
    assert client.post('/register', data={'username': 'test'}).status_code == 400
    invalid = client.post('/register', data={'csrf_token': token(client, '/register'),
        'username': 'x', 'email': 'invalid', 'password': '123', 'confirm_password': 'different'})
    assert invalid.status_code == 422
    assert register(client).status_code == 302
    client.post('/logout', data={'csrf_token': token(client, '/')})
    assert register(client).status_code == 422
    assert client.post('/logout').status_code in (302, 401)


def test_user_subject_isolation(client):
    assert register(client).status_code == 302
    subject_token = token(client, '/subjects')
    assert client.post('/subjects', data={'csrf_token': subject_token, 'name': 'Частен предмет'}).status_code == 302
    client.post('/logout', data={'csrf_token': token(client, '/')})
    assert client.get('/subjects').status_code == 302
    assert 'Частен предмет'.encode() not in client.get('/login').data
    assert register(client, 'maria', 'maria@example.com').status_code == 302
    assert 'Частен предмет'.encode() not in client.get('/subjects').data
