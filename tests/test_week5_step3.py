"""Week 5 / step 3: regression and safety checks without a running Ollama."""
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
from app.services.ai_gateway import DisabledStudyAdviceProvider, AIProviderError


def login_with_subject(client):
    with client.application.app_context():
        user = User(username='final-check', email='final-check@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.flush()
        subject = Subject(name='Математика', user_id=user.id)
        db.session.add(subject)
        db.session.commit()
        user_id, subject_id = user.id, subject.id
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    page = client.get('/ai/plan')
    csrf = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    return user_id, subject_id, csrf


def proposal(subject_id):
    return json.dumps([{'title': 'Упражнения', 'subject_id': subject_id,
                        'date': (date.today() + timedelta(days=1)).isoformat(),
                        'start_time': '17:00', 'end_time': '18:00'}])


def test_disabled_provider_has_actionable_message():
    with pytest.raises(AIProviderError, match='AI_PROVIDER=gemini или ollama'):
        DisabledStudyAdviceProvider().suggest({})


def test_disabled_ai_cannot_save_existing_preview(client):
    user_id, subject_id, csrf = login_with_subject(client)
    client.application.config['AI_PROVIDER'] = 'ollama'
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = proposal(subject_id)
        response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'generate', 'days': '7'})
        assert response.status_code == 200
    client.application.config['AI_PROVIDER'] = 'disabled'
    response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'save', 'days': '7'})
    assert response.status_code == 422
    with client.application.app_context():
        assert StudySession.query.count() == 0


def test_save_rechecks_conflicts_after_preview(client):
    user_id, subject_id, csrf = login_with_subject(client)
    client.application.config['AI_PROVIDER'] = 'ollama'
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = proposal(subject_id)
        assert client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'generate', 'days': '7'}).status_code == 200
    with client.application.app_context():
        from datetime import time
        db.session.add(StudySession(user_id=user_id, subject_id=subject_id,
            title='Existing', session_date=date.today()+timedelta(days=1),
            start_time=time(17), end_time=time(18), status='planned'))
        db.session.commit()
    response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'save', 'days': '7'})
    assert response.status_code == 422
    with client.application.app_context():
        assert StudySession.query.count() == 1


def test_ai_plan_rejects_boolean_subject_id_and_seconds():
    raw = proposal(1)
    item = json.loads(raw)[0]
    item['subject_id'] = True
    with pytest.raises(ValueError):
        parse_ai_plan(json.dumps([item]), today=date.today(), days=7,
                      allowed_subject_ids={1}, existing=[])
    item['subject_id'] = 1
    item['start_time'] = '17:00:30'
    with pytest.raises(ValueError):
        parse_ai_plan(json.dumps([item]), today=date.today(), days=7,
                      allowed_subject_ids={1}, existing=[])


def test_invalid_provider_response_never_writes_database(client):
    _, subject_id, csrf = login_with_subject(client)
    client.application.config['AI_PROVIDER'] = 'ollama'
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = 'invalid json'
        response = client.post('/ai/plan', data={'csrf_token': csrf, 'action': 'generate', 'days': '7'})
        assert response.status_code == 200
        assert 'JSON'.encode() in response.data
    with client.application.app_context():
        assert StudySession.query.count() == 0
