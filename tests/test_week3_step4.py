"""Strategy unit tests and authenticated planner integration tests."""
from datetime import date, time
import re
import pytest
from app import create_app, db
from app.services.study_planning import StudyPlanner, STRATEGIES


def test_strategy_orders_differently():
    today = date(2026, 12, 1)
    goals = [
        {'kind': 'exam', 'title': 'Изпит', 'due': date(2026, 12, 3), 'priority': 0, 'subject_id': 1},
        {'kind': 'task', 'title': 'Задача', 'due': date(2026, 12, 2), 'priority': 3, 'subject_id': 1},
    ]
    assert STRATEGIES['exam'].rank(goals, today)[0]['kind'] == 'exam'
    assert STRATEGIES['priority'].rank(goals, today)[0]['kind'] == 'task'


def test_planner_avoids_overlapping_intervals():
    from types import SimpleNamespace
    today = date(2026, 12, 1)
    goals = [{'kind': 'task', 'title': 'Преговор', 'due': None, 'priority': 3, 'subject_id': 1}]
    existing = [SimpleNamespace(session_date=today, start_time=time(17), end_time=time(18), status='planned')]
    proposals = StudyPlanner(STRATEGIES['priority']).propose(goals, existing, today=today)
    assert len(proposals) == 1
    assert proposals[0]['start_time'] == time(18)


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'plan-test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "plan.db"}'})
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def csrf(client, path):
    page = client.get(path)
    return re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()


def test_planner_auth_and_csrf(client):
    assert client.get('/schedule/plan').status_code == 302
    assert client.post('/schedule/plan', data={'strategy': 'exam'}).status_code == 302
    client.post('/register', data={'csrf_token': csrf(client, '/register'),
        'username': 'planner', 'email': 'planner@example.com',
        'password': 'password123', 'confirm_password': 'password123'})
    assert client.get('/schedule/plan').status_code == 200
    assert client.get('/schedule/plan?strategy=invalid').status_code == 422
    assert client.post('/schedule/plan', data={'strategy': 'exam'}).status_code == 400
    assert client.get('/schedule').status_code == 200
