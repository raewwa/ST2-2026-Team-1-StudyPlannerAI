"""Week 4 / step 3: security and integration regression checks."""
import re
import pytest
from app import db
from app.models.user import User
from app.models.task import Task
from app.services.ai_gateway import DisabledStudyAdviceProvider


def register(client, name):
    page = client.get('/register')
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    result = client.post('/register', data={
        'csrf_token': token, 'username': name, 'email': f'{name}@example.com',
        'password': 'password123', 'confirm_password': 'password123'})
    assert result.status_code == 302


def test_security_headers_and_cookie_configuration(client):
    response = client.get('/login')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert client.application.config['SESSION_COOKIE_HTTPONLY'] is True
    assert client.application.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_mutating_endpoints_require_login_and_csrf(client):
    assert client.post('/tasks', data={'title': 'Bad'}).status_code == 302
    register(client, 'securitytest')
    assert client.post('/tasks', data={'title': 'Bad'}).status_code == 400
    assert client.post('/logout').status_code == 400
    with client.application.app_context():
        assert Task.query.count() == 0


def test_passwords_are_hashed_and_account_is_scoped(client):
    register(client, 'hashcheck')
    with client.application.app_context():
        user = User.query.filter_by(email='hashcheck@example.com').one()
        assert user.password_hash != 'password123'
        assert user.check_password('password123')
        assert not user.check_password('wrong-password')


def test_ai_boundary_is_disabled_until_week_five():
    with pytest.raises(RuntimeError, match='Week 5'):
        DisabledStudyAdviceProvider().suggest({'topic': 'Math'})
