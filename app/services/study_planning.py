"""Strategy pattern: interchangeable deterministic planning priorities; no LLM.

The context chooses a strategy at runtime. Both algorithms return a new ordered
list and never mutate the database. All data is supplied from owner-scoped repos.
"""
from datetime import date, timedelta, time


class StudyPlanningStrategy:
    """Strategy interface for ordering actionable study goals."""
    key = None
    label = None

    def rank(self, goals, today):
        raise NotImplementedError


class ExamDeadlineStrategy(StudyPlanningStrategy):
    """Prioritize the nearest upcoming exam, then tasks with deadlines."""
    key = 'exam'
    label = 'Най-близък изпит'

    def rank(self, goals, today):
        return sorted(goals, key=lambda g: (
            0 if g['kind'] == 'exam' else 1,
            g['due'] or date.max,
            g['title'].casefold(),
        ))


class TaskPriorityStrategy(StudyPlanningStrategy):
    """Prioritize high-priority tasks, then upcoming exams."""
    key = 'priority'
    label = 'Приоритет на задачите'

    def rank(self, goals, today):
        return sorted(goals, key=lambda g: (
            0 if g['kind'] == 'task' else 1,
            -g['priority'],
            g['due'] or date.max,
            g['title'].casefold(),
        ))


STRATEGIES = {item.key: item for item in (ExamDeadlineStrategy(), TaskPriorityStrategy())}


class StudyPlanner:
    """Context: chooses a Strategy and proposes free one-hour slots."""

    def __init__(self, strategy):
        self.strategy = strategy

    def propose(self, goals, existing, today=None, days=7, limit=6):
        today = today or date.today()
        ranked = self.strategy.rank(goals, today)
        occupied = {(s.session_date, s.start_time, s.end_time)
                    for s in existing if s.status != 'cancelled'}
        proposals = []
        for goal in ranked:
            if len(proposals) >= limit:
                break
            for offset in range(days):
                day = today + timedelta(days=offset)
                # Do not schedule study after a known exam or overdue deadline.
                if goal['due'] is not None and day > goal['due']:
                    continue
                for hour in (17, 18, 19):
                    start, end = time(hour, 0), time(hour + 1, 0)
                    if any(d == day and a < end and b > start for d, a, b in occupied):
                        continue
                    proposal = {'title': 'Подготовка: ' + goal['title'],
                                'subject_id': goal['subject_id'],
                                'session_date': day, 'start_time': start,
                                'end_time': end, 'status': 'planned',
                                'description': 'Предложение по стратегия: ' + self.strategy.label}
                    proposals.append(proposal)
                    occupied.add((day, start, end))
                    break
                else:
                    continue
                break
        return proposals
