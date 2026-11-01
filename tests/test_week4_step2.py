"""Week 4 / step 2: owner-safe advanced filters and invalid query handling."""
import re
from app import db
from app.models.task import Task
from app.models.user import User
from app.models.exam import Exam
from datetime import date, time


def login_user(client):
    page = client.get('/register')
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    response = client.post('/register', data={'csrf_token': token, 'username': 'week4two',
        'email': 'week4two@example.com', 'password': 'password123', 'confirm_password': 'password123'})
    assert response.status_code == 302


def test_task_search_sort_and_validation(client):
    login_user(client)
    with client.application.app_context():
        user = User.query.filter_by(email='week4two@example.com').one()
        db.session.add_all([Task(title='Алгебра упражнение', user_id=user.id, priority='high'),
                            Task(title='Физика упражнение', user_id=user.id, priority='low')])
        db.session.commit()
    html = client.get('/tasks?search=Алгебра&sort=priority').get_data(as_text=True)
    assert 'Алгебра упражнение' in html and 'Физика упражнение' not in html
    assert 'Невалидно сортиране' in client.get('/tasks?sort=unknown').get_data(as_text=True)


def test_exam_filters_and_schedule_controls(client):
    login_user(client)
    assert 'exam_search' in client.get('/exams').get_data(as_text=True)
    assert 'Невалиден статус' in client.get('/exams?status=invalid').get_data(as_text=True)
    assert 'session_status' in client.get('/schedule').get_data(as_text=True)
    assert 'Невалидно сортиране' in client.get('/schedule?sort=wrong').get_data(as_text=True)
