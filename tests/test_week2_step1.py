"""Week 2 / step 1: user model, password hashing, migration and UI."""
import re
import pytest
from sqlalchemy import inspect, text
from app import create_app, db, load_user
from app.models.user import User
from app.models.subject import Subject


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "week2.db"}'})
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_user_model_and_password_hash(app):
    with app.app_context():
        user = User(username='student', email='student@example.com')
        user.set_password('secure-pass-123')
        assert user.password_hash != 'secure-pass-123'
        assert user.check_password('secure-pass-123')
        assert not user.check_password('wrong')
        db.session.add(user)
        db.session.commit()
        assert load_user(str(user.id)).id == user.id
        assert load_user('not-a-number') is None
        assert {'users', 'subjects'} <= set(inspect(db.engine).get_table_names())


def test_subject_owner_relationship(app):
    with app.app_context():
        user = User(username='maria', email='maria@example.com')
        user.set_password('password123')
        user.subjects.append(Subject(name='Алгебра', semester=2))
        db.session.add(user)
        db.session.commit()
        assert Subject.query.filter_by(user_id=user.id).one().name == 'Алгебра'


def test_existing_week1_subjects_survive_upgrade(tmp_path):
    from sqlalchemy import create_engine
    path = tmp_path / 'legacy.db'
    engine = create_engine(f'sqlite:///{path}')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE subjects (id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, description TEXT, semester INTEGER, created_at DATETIME NOT NULL)'))
        connection.execute(text("INSERT INTO subjects (name, semester, created_at) VALUES ('Физика', 1, '2026-10-01')"))
    engine.dispose()
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}'})
    with app.app_context():
        assert Subject.query.one().name == 'Физика'
        assert Subject.query.one().user_id is None
        assert 'user_id' in {c['name'] for c in inspect(db.engine).get_columns('subjects')}
        db.session.remove()
        db.engine.dispose()
    # Running initialization again must be idempotent.
    app2 = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}'})
    with app2.app_context():
        assert Subject.query.count() == 1


def test_active_nav_style_and_existing_pages(app):
    with app.test_client() as client:
        assert client.get('/').status_code == 200
        assert client.get('/subjects').status_code == 200
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/style.css').read_text()
    assert 'background-color: #bee9e8' in css
    assert '.nav-pills .nav-link.sidebar-link.active' in css
