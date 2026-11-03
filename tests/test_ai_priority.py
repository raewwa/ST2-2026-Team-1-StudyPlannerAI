from datetime import date
from app.services.ai_priority import build_study_allocations


def test_high_priority_and_near_exam_get_more_time():
    ctx = {'today': '2026-11-03', 'subjects': [{'id': 1, 'name': 'Math'}, {'id': 2, 'name': 'History'}],
           'tasks': [{'subject_id': 1, 'title': 'Calculus', 'priority': 'high', 'status': 'pending', 'due': '2026-11-04'},
                     {'subject_id': 2, 'title': 'Reading', 'priority': 'low', 'status': 'pending', 'due': '2026-12-01'}],
           'exams': [{'subject_id': 1, 'title': 'Math final', 'date': '2026-11-05', 'status': 'upcoming'}]}
    result = build_study_allocations(ctx)
    assert result[0]['subject_id'] == 1
    assert result[0]['target_minutes'] > result[1]['target_minutes']
    assert sum(x['target_sessions'] for x in result) <= 8


def test_completed_tasks_and_past_exams_ignored():
    ctx = {'today': '2026-11-03', 'subjects': [{'id': 1, 'name': 'Math'}, {'id': 2, 'name': 'History'}],
           'tasks': [{'subject_id': 1, 'priority': 'high', 'status': 'completed', 'due': None}],
           'exams': [{'subject_id': 1, 'date': '2026-10-01', 'status': 'upcoming'}]}
    result = build_study_allocations(ctx)
    assert {x['subject_id'] for x in result} == {1, 2}
