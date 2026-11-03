import json
from datetime import date, time
from types import SimpleNamespace
from app.services.ai_planning import parse_ai_plan, repair_ai_plan_timing

TODAY = date(2026, 11, 3)

def plan(*items):
    return json.dumps({'sessions': list(items)})

def item(start, end, subject_id=1):
    return {'title': 'Review calculus', 'subject_id': subject_id, 'date': '2026-11-04',
            'start_time': start, 'end_time': end}

def test_short_session_is_repaired_and_validated():
    raw = repair_ai_plan_timing(plan(item('17:00', '17:15')), today=TODAY, days=7, existing=[])
    result = parse_ai_plan(raw, today=TODAY, days=7, allowed_subject_ids={1}, existing=[])
    assert result[0]['start_time'] == time(17)
    assert result[0]['end_time'] == time(18)

def test_long_session_is_repaired():
    raw = repair_ai_plan_timing(plan(item('17:00', '20:00')), today=TODAY, days=7, existing=[])
    result = parse_ai_plan(raw, today=TODAY, days=7, allowed_subject_ids={1}, existing=[])
    assert result[0]['end_time'] == time(18)

def test_overlap_relocated_without_overwriting_existing():
    existing = [SimpleNamespace(session_date=date(2026,11,4), start_time=time(17),
                                end_time=time(18), status='planned')]
    raw = repair_ai_plan_timing(plan(item('17:00', '17:15'), item('17:00', '17:20')),
                                today=TODAY, days=7, existing=existing)
    result = parse_ai_plan(raw, today=TODAY, days=7, allowed_subject_ids={1}, existing=existing)
    assert len(result) == 2
    assert all(not (x['start_time'] < time(18) and x['end_time'] > time(17)) for x in result)

def test_foreign_subject_still_rejected():
    raw = repair_ai_plan_timing(plan(item('17:00', '17:15', 999)), today=TODAY, days=7, existing=[])
    try:
        parse_ai_plan(raw, today=TODAY, days=7, allowed_subject_ids={1}, existing=[])
    except ValueError as exc:
        assert 'subject' in str(exc)
    else:
        raise AssertionError('Foreign subject must be rejected')
