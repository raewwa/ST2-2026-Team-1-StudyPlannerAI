"""Week 3 / Step 2: schedule CRUD, overlap detection and account isolation."""
import re
import pytest
from app import create_app, db
from app.models.study_session import StudySession
from app.models.subject import Subject


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'schedule-test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "schedule.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def token(client, url):
    result = re.search(rb'name="csrf_token" value="([^"]+)"', client.get(url).data)
    assert result
    return result.group(1).decode()


def register(client, name):
    return client.post('/register', data={'csrf_token': token(client, '/register'),
        'username': name, 'email': f'{name}@example.com',
        'password': 'password123', 'confirm_password': 'password123'})


def subject(client):
    assert client.post('/subjects', data={'csrf_token': token(client, '/subjects'),
                                         'name': 'Физика'}).status_code == 302
    with client.application.app_context():
        return Subject.query.order_by(Subject.id.desc()).first().id


def add(client, sid, **changes):
    data = {'csrf_token': token(client, '/schedule'), 'title': 'Преговор',
            'subject_id': str(sid), 'session_date': '2026-12-14',
            'start_time': '09:00', 'end_time': '10:00', 'status': 'planned'}
    data.update(changes)
    return client.post('/schedule', data=data)


def test_schedule_requires_login(client):
    assert client.get('/schedule').status_code == 302
    assert client.post('/schedule', data={}).status_code == 302


def test_schedule_crud(client):
    register(client, 'student1')
    sid = subject(client)
    assert add(client, sid).status_code == 302
    page = client.get('/schedule?week=2026-12-14').get_data(as_text=True)
    assert 'Преговор' in page
    with client.application.app_context():
        item_id = StudySession.query.one().id
    url = f'/schedule/{item_id}/edit'
    assert client.get(url).status_code == 200
    assert client.post(url, data={}).status_code == 400
    assert client.post(url, data={'csrf_token': token(client, url), 'title': 'Решаване на задачи',
        'subject_id': str(sid), 'session_date': '2026-12-14',
        'start_time': '10:00', 'end_time': '11:00', 'status': 'completed'}).status_code == 302
    with client.application.app_context():
        assert StudySession.query.one().title == 'Решаване на задачи'
    assert client.post(f'/schedule/{item_id}/delete', data={}).status_code == 400
    assert client.post(f'/schedule/{item_id}/delete', data={
        'csrf_token': token(client, '/schedule')}).status_code == 302
    with client.application.app_context():
        assert StudySession.query.count() == 0


def test_validation_and_overlap(client):
    register(client, 'student2')
    sid = subject(client)
    assert add(client, sid).status_code == 302
    assert add(client, sid, start_time='09:30', end_time='10:30').status_code == 422
    assert add(client, sid, start_time='10:00', end_time='11:00').status_code == 302
    assert add(client, sid, start_time='12:00', end_time='11:00').status_code == 422
    assert add(client, sid, start_time='25:00').status_code == 422
    assert add(client, sid, session_date='invalid').status_code == 422
    assert add(client, sid, subject_id='9999').status_code == 422
    assert add(client, sid, status='unknown').status_code == 422
    with client.application.app_context():
        assert StudySession.query.count() == 2


def test_owner_isolation(client):
    register(client, 'student3')
    sid = subject(client)
    assert add(client, sid).status_code == 302
    with client.application.app_context():
        item_id = StudySession.query.one().id
    client.post('/logout', data={'csrf_token': token(client, '/schedule')})
    register(client, 'student4')
    assert 'data-session-id=' not in client.get('/schedule?week=2026-12-14').get_data(as_text=True)
    assert client.get(f'/schedule/{item_id}/edit').status_code == 404
    assert client.post(f'/schedule/{item_id}/delete', data={}).status_code == 404
    assert add(client, sid).status_code == 422
