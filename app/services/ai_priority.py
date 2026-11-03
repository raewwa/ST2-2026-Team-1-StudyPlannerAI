"""Deterministic, explainable workload weights for Ollama study plans.

Weights reflect task priority and proximity to deadlines/exams. They are
recommendations, not a replacement for the existing session safety checks.
"""
from datetime import date

PRIORITY_WEIGHT = {'high': 6.0, 'medium': 3.0, 'low': 1.0}


def _urgency(due, today):
    if not due:
        return 1.0
    remaining = (date.fromisoformat(due) - today).days
    if remaining < 0:
        return 0.0
    if remaining <= 1:
        return 3.0
    if remaining <= 3:
        return 2.5
    if remaining <= 7:
        return 2.0
    if remaining <= 14:
        return 1.5
    return 1.0


def build_study_allocations(context):
    """Return per-subject target sessions (1..8 total), largest-remainder rounding.

    Excludes completed tasks and past exams. Each eligible subject receives a
    score from task priority/deadlines and upcoming exam urgency. Subjects with
    no goals receive no slots unless *all* subjects lack goals.
    """
    today = date.fromisoformat(context['today'])
    ids = [s['id'] for s in context['subjects']]
    scores = {sid: 0.0 for sid in ids}
    reasons = {sid: [] for sid in ids}
    for task in context.get('tasks', []):
        sid = task.get('subject_id')
        if sid not in scores or task.get('status') in ('completed', 'done', 'cancelled'):
            continue
        due = task.get('due')
        if due and date.fromisoformat(due) < today:
            # Overdue unfinished tasks still deserve attention.
            factor = 2.0
        else:
            factor = _urgency(due, today)
        weight = PRIORITY_WEIGHT.get(str(task.get('priority', '')).lower(), 1.0) * factor
        scores[sid] += weight
        reasons[sid].append(f"task '{task.get('title', '')[:60]}' ({task.get('priority')}, due {due or 'unspecified'})")
    for exam in context.get('exams', []):
        sid = exam.get('subject_id')
        if sid not in scores or exam.get('status') in ('completed', 'cancelled'):
            continue
        exam_day = exam.get('date')
        factor = _urgency(exam_day, today)
        if not factor:
            continue
        scores[sid] += 5.0 * factor
        reasons[sid].append(f"exam '{exam.get('title', '')[:60]}' ({exam_day})")
    if not any(scores.values()):
        scores = {sid: 1.0 for sid in ids}
    ranked = sorted(ids, key=lambda sid: (-scores[sid], sid))
    active = [sid for sid in ranked if scores[sid] > 0]
    count = min(8, max(1, len(active) * 2))
    total = sum(scores[sid] for sid in active)
    # Give every eligible subject one session when capacity allows, then
    # distribute the remaining time proportionally to urgency and priority.
    active = active[:count]
    slots = {sid: 1 for sid in active}
    remaining = count - len(active)
    exact = {sid: remaining * scores[sid] / total for sid in active}
    for sid in active:
        slots[sid] += int(exact[sid])
    left = count - sum(slots.values())
    for sid in sorted(active, key=lambda x: (-(exact[x] - int(exact[x])), -scores[x], x))[:left]:
        slots[sid] += 1
    return [dict(subject_id=sid, subject=next(s['name'] for s in context['subjects'] if s['id'] == sid),
                 score=round(scores[sid], 2), target_sessions=slots[sid],
                 target_minutes=slots[sid] * 60, reasons=reasons[sid][:5])
            for sid in active if slots[sid]]
