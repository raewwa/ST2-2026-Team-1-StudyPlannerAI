"""Week 4 dashboard and schedule visual regression tests."""
from datetime import date, timedelta
from app import db
from app.models.exam import Exam
from app.models.study_session import StudySession
from app.models.subject import Subject
from app.models.task import Task
from app.models.user import User


def test_dashboard_uses_only_current_users_data(client):
    # Existing shared fixture supplies a Flask client; use app context for isolation.
    with client.application.app_context():
        a = User(username='dashboard_a', email='dashboard_a@example.com')
        b = User(username='dashboard_b', email='dashboard_b@example.com')
        a.set_password('password123')
        b.set_password('password123')
        db.session.add_all([a, b])
        db.session.flush()
        db.session.add(Task(title='Only B task', user_id=b.id, status='pending'))
        db.session.commit()
    response = client.get('/')
    assert response.status_code == 302  # Unauthenticated visitors cannot see stats.


def test_legacy_progress_text_is_absent(client):
    from test_week2_step5 import register
    register(client, 'dash_w4')
    html = client.get('/').get_data(as_text=True)
    assert 'Седмица 2 · Завършена' not in html
    assert 'Напредък по проекта' not in html
    assert 'Предстоящи събития' in html
    assert 'Учебно време тази седмица' in html


def test_schedule_buttons_have_semantic_classes(client):
    from test_week2_step5 import register
    register(client, 'schedule_w4')
    html = client.get('/schedule').get_data(as_text=True)
    assert 'btn-schedule-nav' in html
    assert 'btn-plan-study' in html
    assert 'btn-schedule-add' in html
