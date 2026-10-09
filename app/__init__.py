"""Application factory and extension initialization (MVC bootstrap)."""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()
db = SQLAlchemy()


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
    from app.controllers.main_controller import main_bp
    app.register_blueprint(main_bp)
    with app.app_context():
        from app.models.subject import Subject  # noqa: F401 - register model
        db.create_all()
    return app
