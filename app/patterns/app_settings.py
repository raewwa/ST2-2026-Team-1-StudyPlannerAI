"""Singleton design pattern: one shared, immutable application settings object.

Why: the application needs a consistent set of UI/filter settings. The class
returns the same instance for repeated construction. Database sessions and
connections are intentionally NOT singletons: Flask-SQLAlchemy manages them.
"""
from threading import Lock


class AppSettings:
    """Thread-safe Singleton for constant, application-wide settings.

    Pattern: Singleton (creational). `__new__` creates the instance only once.
    Do not put request/user-specific or mutable state in this object.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    object.__setattr__(instance, "max_search_length", 120)
                    object.__setattr__(instance, "min_semester", 1)
                    object.__setattr__(instance, "max_semester", 12)
                    cls._instance = instance
        return cls._instance

    def __setattr__(self, key, value):
        raise AttributeError("AppSettings is immutable")
