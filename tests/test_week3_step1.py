"""Week 3 / Step 1: exams CRUD, validation, CSRF and ownership."""
import re
import pytest
from app import create_app, db
from app.models.exam import Exam

@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'exams-test', 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "exams.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()

def token(client, path):
    match = re.search(rb'name="csrf_token" value="([^"]+)"', client.get(path).data)
    assert match
    return match.group(1).decode()

def register(client, name):
    return client.post('/register', data={'csrf_token': token(client, '/register'), 'username': name,
        'email': f'{name}@example.com', 'password': 'password123', 'confirm_password': 'password123'})

def subject(client, name='Математика'):
    assert client.post('/subjects', data={'csrf_token': token(client, '/subjects'), 'name': name}).status_code == 302
    from app.models.subject import Subject
    with client.application.app_context():
        return Subject.query.order_by(Subject.id.desc()).first().id

def create_exam(client, subject_id, **overrides):
    payload = dict(csrf_token=token(client, '/exams'), title='Алгебра', subject_id=str(subject_id),
                   exam_date='2026-12-15', exam_time='10:30', status='upcoming')
    payload.update(overrides)
    return client.post('/exams', data=payload)

def test_exams_require_login(client):
    assert client.get('/exams').status_code == 302
    assert client.post('/exams', data={}).status_code == 302

def test_crud_and_csrf(client):
    register(client, 'examuser')
    sid = subject(client)
    assert create_exam(client, sid).status_code == 302
    with client.application.app_context():
        exam_id = Exam.query.one().id
    assert 'Алгебра' in client.get('/exams').get_data(as_text=True)
    path = f'/exams/{exam_id}/edit'
    assert client.get(path).status_code == 200
    assert client.post(path, data={'title':'No CSRF'}).status_code == 400
    assert client.post(path, data={'csrf_token':token(client,path), 'title':'Геометрия',
        'subject_id':str(sid), 'exam_date':'2026-12-16', 'exam_time':'11:00', 'status':'completed'}).status_code == 302
    with client.application.app_context():
        assert Exam.query.one().title == 'Геометрия'
        assert Exam.query.one().status == 'completed'
    assert client.post(f'/exams/{exam_id}/delete', data={}).status_code == 400
    assert client.post(f'/exams/{exam_id}/delete', data={'csrf_token':token(client,'/exams')}).status_code == 302
    with client.application.app_context():
        assert Exam.query.count() == 0

def test_validation(client):
    register(client, 'validexam')
    sid = subject(client)
    assert create_exam(client, sid, exam_date='not-a-date').status_code == 422
    assert create_exam(client, sid, exam_time='28:00').status_code == 422
    assert create_exam(client, sid, status='unknown').status_code == 422
    assert create_exam(client, '9999').status_code == 422
    assert create_exam(client, sid, title='').status_code == 422
    with client.application.app_context():
        assert Exam.query.count() == 0

def test_owner_isolation(client):
    register(client, 'ownerexam')
    sid = subject(client)
    create_exam(client, sid)
    with client.application.app_context():
        exam_id = Exam.query.one().id
    client.post('/logout', data={'csrf_token': token(client, '/exams')})
    register(client, 'otherexam')
    assert 'Алгебра' not in client.get('/exams').get_data(as_text=True)
    assert client.get(f'/exams/{exam_id}/edit').status_code == 404
    assert client.post(f'/exams/{exam_id}/edit', data={}).status_code == 404
    assert client.post(f'/exams/{exam_id}/delete', data={}).status_code == 404
    assert create_exam(client, sid).status_code == 422
