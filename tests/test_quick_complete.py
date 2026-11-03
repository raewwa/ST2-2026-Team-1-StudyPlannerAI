"""Quick completion buttons: owner isolation, CSRF, and reversible status."""
import re
from app.models.subject import Subject


def token(client, path):
    match = re.search(rb'name="csrf_token" value="([^"]+)"', client.get(path).data)
    assert match
    return match.group(1).decode()


def register(client, name):
    return client.post('/register', data={'csrf_token': token(client, '/register'), 'username': name,
        'email': f'{name}@example.com', 'password': 'password123', 'confirm_password': 'password123'})


def subject(client):
    assert client.post('/subjects', data={'csrf_token': token(client, '/subjects'), 'name': 'Math'}).status_code == 302
    with client.application.app_context():
        return Subject.query.order_by(Subject.id.desc()).first().id


def create_exam(client, subject_id):
    return client.post('/exams', data={'csrf_token': token(client, '/exams'), 'title': 'Algebra',
        'subject_id': str(subject_id), 'exam_date': '2026-12-15', 'exam_time': '10:30', 'status': 'upcoming'})
from app.models.exam import Exam


def test_exam_quick_complete(client):
    register(client, 'quickexam')
    sid = subject(client)
    assert create_exam(client, sid).status_code == 302
    with client.application.app_context():
        exam_id = Exam.query.one().id
    path = f'/exams/{exam_id}/toggle'
    assert client.post(path).status_code == 400
    assert 'Mark Complete' in client.get('/exams').get_data(as_text=True)
    assert client.post(path, data={'csrf_token': token(client, '/exams')}).status_code == 302
    with client.application.app_context():
        assert Exam.query.one().status == 'completed'
    assert 'Reopen Exam' in client.get('/exams').get_data(as_text=True)
    assert client.post(path, data={'csrf_token': token(client, '/exams')}).status_code == 302
    with client.application.app_context():
        assert Exam.query.one().status == 'upcoming'


def test_exam_quick_complete_owner_isolation(client):
    register(client, 'quickowner')
    sid = subject(client)
    create_exam(client, sid)
    with client.application.app_context():
        exam_id = Exam.query.one().id
    client.post('/logout', data={'csrf_token': token(client, '/exams')})
    register(client, 'quickother')
    assert client.post(f'/exams/{exam_id}/toggle', data={'csrf_token': token(client, '/exams')}).status_code == 404
    with client.application.app_context():
        assert Exam.query.one().status == 'upcoming'
