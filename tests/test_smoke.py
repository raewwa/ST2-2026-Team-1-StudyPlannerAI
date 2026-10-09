import pytest
from app import create_app, db


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "test.db"}'})
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize('route', ['/', '/subjects', '/tasks', '/exams', '/schedule', '/login', '/register'])
def test_pages_load(client, route):
    response = client.get(route)
    assert response.status_code == 200
    assert b'AI Study Planner' in response.data


def test_subjects_table_created(client):
    from sqlalchemy import inspect
    from app import db
    with client.application.app_context():
        assert 'subjects' in inspect(db.engine).get_table_names()
