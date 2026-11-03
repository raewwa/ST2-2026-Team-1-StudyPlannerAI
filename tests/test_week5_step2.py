import json
import re
from datetime import date, timedelta
from unittest.mock import patch
import pytest
from app import db
from app.models.user import User
from app.models.subject import Subject
from app.models.study_session import StudySession
from app.services.ai_planning import parse_ai_plan


def sign_in(client):
    with client.application.app_context():
        user = User(username='plan-test', email='plan-test@example.com')
        user.set_password('testpassword123')
        db.session.add(user)
        db.session.commit()
        subject = Subject(name='Математика', user_id=user.id)
        db.session.add(subject)
        db.session.commit()
        uid, sid = user.id, subject.id
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    return uid, sid


def token(client):
    html = client.get('/ai/plan').data
    return re.search(rb'name="csrf_token" value="([^"]+)"', html).group(1).decode()


def ai_json(subject_id):
    return json.dumps([{'title': 'Преговор', 'subject_id': subject_id,
                        'date': (date.today() + timedelta(days=1)).isoformat(),
                        'start_time': '17:00', 'end_time': '18:00'}])


def test_ai_plan_requires_login(client):
    assert client.get('/ai/plan').status_code == 302


def test_ai_plan_csrf_and_period(client):
    sign_in(client)
    assert client.post('/ai/plan').status_code == 400
    assert client.post('/ai/plan', data={'csrf_token': token(client), 'days': '90'}).status_code == 422


def test_ai_plan_preview_then_save(client):
    uid, sid = sign_in(client)
    client.application.config['AI_PROVIDER'] = 'ollama'
    csrf = token(client)
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = ai_json(sid)
        response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'generate', 'days': '7'})
        assert response.status_code == 200
        assert 'Преговор'.encode() in response.data
        context = factory.return_value.suggest.call_args.args[0]
        assert context['days'] == 7
        assert context['subjects'][0]['id'] == sid
    with client.application.app_context():
        assert StudySession.query.count() == 0
    response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'save', 'days': '7'})
    assert response.status_code == 302
    with client.application.app_context():
        item = StudySession.query.one()
        assert item.user_id == uid
        assert item.subject_id == sid
    assert client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'save', 'days': '7'}).status_code == 422


def test_ai_plan_rejects_foreign_subject_and_overlap(client):
    _, sid = sign_in(client)
    client.application.config['AI_PROVIDER'] = 'ollama'
    csrf = token(client)
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = ai_json(sid + 999)
        response = client.post('/ai/plan', data={'csrf_token': csrf, 'days': '7'})
        assert 'не принадлежи'.encode() in response.data
    with client.application.app_context():
        assert StudySession.query.count() == 0
    with pytest.raises(ValueError, match='застъпващи'):
        parse_ai_plan(json.dumps([json.loads(ai_json(sid))[0]] * 2), today=date.today(),
                      days=7, allowed_subject_ids={sid}, existing=[])
