"""Flask application factory and database/authentication extensions."""
import os
from pathlib import Path
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from dotenv import load_dotenv

load_dotenv()
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Моля, влезте в профила си.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback; never trust a nonnumeric session user id."""
    from app.models.user import User
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def upgrade_legacy_subjects_schema():
    """Non-destructive SQLite migration for existing Week 1 databases.

    SQLite ADD COLUMN keeps old subjects; NULL ownership is temporary until
    login/registration and user-scoped data are implemented in step 2.
    """
    inspector = inspect(db.engine)
    if 'subjects' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('subjects')}
    if 'user_id' not in columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE subjects ADD COLUMN user_id INTEGER REFERENCES users(id)'))
    # CREATE INDEX IF NOT EXISTS works for both old and fresh SQLite files.
    with db.engine.begin() as connection:
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_subjects_user_id ON subjects (user_id)'))


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev-only-change-me'),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///study_planner.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    from app.models.user import User  # noqa: F401
    from app.models.subject import Subject  # noqa: F401
    from app.controllers.main_controller import main_bp
    app.register_blueprint(main_bp)
    with app.app_context():
        # Create users before upgrading existing subjects for their FK.
        User.__table__.create(bind=db.engine, checkfirst=True)
        upgrade_legacy_subjects_schema()
        db.create_all()
    return app
