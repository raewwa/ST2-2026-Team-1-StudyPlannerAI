"""Week 5 integration boundary (no model requests are made in Week 4).

The controller will depend on a StudyAdviceProvider abstraction instead of
calling an LLM SDK directly. This keeps AI optional and testable.
"""
from abc import ABC, abstractmethod


class StudyAdviceProvider(ABC):
    """Interface for future local/remote LLM implementations."""

    @abstractmethod
    def suggest(self, context: dict) -> str:
        """Return study advice for already-authorized user data."""


class DisabledStudyAdviceProvider(StudyAdviceProvider):
    """Safe default: no external network or AI calls."""

    def suggest(self, context: dict) -> str:
        raise RuntimeError('AI integration is planned for Week 5.')
