from unittest.mock import patch
import re
import pytest
from app.services.ai_gateway import (create_advice_provider, DisabledStudyAdviceProvider,
                                     OllamaStudyAdviceProvider, AIProviderError)


def test_provider_factory_and_local_url_guard():
    assert isinstance(create_advice_provider({'AI_PROVIDER': 'disabled'}), DisabledStudyAdviceProvider)
    assert isinstance(create_advice_provider({'AI_PROVIDER': 'ollama'}), OllamaStudyAdviceProvider)
    with pytest.raises(ValueError):
        OllamaStudyAdviceProvider('https://example.com')
    with pytest.raises(ValueError):
        create_advice_provider({'AI_PROVIDER': 'unknown'})


def test_ai_route_requires_login(client):
    assert client.get('/ai/advice').status_code == 302


def test_ai_route_csrf_and_mocked_provider(client):
    from app.models.user import User
    from app import db
    with client.application.app_context():
        user = User(username='ai-test', email='ai-test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        uid = user.id
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    client.application.config['AI_PROVIDER'] = 'ollama'
    assert client.post('/ai/advice').status_code == 400
    html = client.get('/ai/advice').data
    token = re.search(rb'name="csrf_token" value="([^"]+)"', html).group(1).decode()
    with patch('app.controllers.main_controller.create_advice_provider') as factory:
        factory.return_value.suggest.return_value = 'Учи по 30 минути.'
        response = client.post('/ai/advice', data={'csrf_token': token})
        assert response.status_code == 200
        assert 'Учи по 30 минути.'.encode() in response.data
        context = factory.return_value.suggest.call_args.args[0]
        assert set(context) == {'subjects', 'tasks', 'exams'}
