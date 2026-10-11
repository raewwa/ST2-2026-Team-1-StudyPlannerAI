"""Week 1 acceptance tests: INSERT, SELECT with Filter, Singleton."""
import re
import pytest
from app import create_app, db
from app.models.subject import Subject
from app.patterns.app_settings import AppSettings


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-key',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "filters.db"}'})
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def add_subject(client, name, semester):
    response = client.get('/subjects')
    token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()
    result = client.post('/subjects', data={'csrf_token': token, 'name': name,
                                           'semester': str(semester)})
    assert result.status_code == 302


def test_filter_by_name_semester_and_combined(client):
    add_subject(client, 'Математика', 1)
    add_subject(client, 'Математика II', 2)
    add_subject(client, 'Физика', 2)
    assert len(client.get('/subjects?search=математика').data.split('class="list-group-item')) == 3
    assert len(client.get('/subjects?semester=2').data.split('class="list-group-item')) == 3
    response = client.get('/subjects?search=МАТЕМАТИКА&semester=2')
    assert response.status_code == 200
    assert 'Математика II'.encode() in response.data
    assert 'Физика'.encode() not in response.data
    assert 'Намерени: 1'.encode() in response.data


def test_empty_results_and_bad_filters(client):
    add_subject(client, 'История', 1)
    response = client.get('/subjects?search=несъществуващ')
    assert 'Няма предмети по избраните критерии.'.encode() in response.data
    for url in ('/subjects?semester=999', '/subjects?semester=abc',
                '/subjects?search=' + 'x' * 121):
        response = client.get(url)
        assert response.status_code == 200
        assert 'Намерени: 0'.encode() in response.data


def test_literal_wildcards(client):
    add_subject(client, '100% Математика', 1)
    add_subject(client, 'Физика', 2)
    response = client.get('/subjects?search=%25')
    assert '100% Математика'.encode() in response.data
    assert 'Физика'.encode() not in response.data


def test_singleton_identity_immutable_and_values():
    first = AppSettings()
    assert first is AppSettings()
    assert first.max_search_length == 120
    assert first.min_semester == 1
    assert first.max_semester == 12
    with pytest.raises(AttributeError):
        first.max_search_length = 999
