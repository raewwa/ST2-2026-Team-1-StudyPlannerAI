"""Validate AI-proposed study sessions before they can enter the database.

The LLM is untrusted: dates, ownership, hours and overlaps are validated locally.
"""
import json
from datetime import date, timedelta, time


def parse_ai_plan(raw, *, today, days, allowed_subject_ids, existing):
    """Parse a strict JSON array and return safe, nonoverlapping session dictionaries."""
    if not isinstance(raw, str) or len(raw) > 12000:
        raise ValueError('Invalid AI response.')
    content = raw.strip()
    if content.startswith('```'):
        lines = content.splitlines()
        content = '\n'.join(lines[1:-1]).strip() if len(lines) >= 3 else content
    try:
        payload = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError('AI did not return valid JSON. Please try again.') from exc
    if isinstance(payload, dict):
        payload = payload.get('sessions')
    if not isinstance(payload, list) or not 1 <= len(payload) <= 8:
        raise ValueError('AI plan must contain 1 to 8 sessions.')
    busy = [(x.session_date, x.start_time, x.end_time) for x in existing if x.status != 'cancelled']
    proposals = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError('Invalid study session in AI plan.')
        try:
            if isinstance(entry['subject_id'], bool) or str(entry['subject_id']).strip() != str(int(entry['subject_id'])):
                raise ValueError('Invalid subject id')
            subject_id = int(entry['subject_id'])
            day = date.fromisoformat(entry['date'])
            start = time.fromisoformat(entry['start_time'])
            end = time.fromisoformat(entry['end_time'])
            title = entry['title'].strip()
            if start.second or start.microsecond or end.second or end.microsecond:
                raise ValueError('Invalid seconds in time')
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError('AI plan contains invalid dates, times or subjects.') from exc
        if subject_id not in allowed_subject_ids:
            raise ValueError('AI plan includes a subject that does not belong to your account.')
        if not today <= day < today + timedelta(days=days):
            raise ValueError('AI plan contains a date outside the selected period.')
        if not 1 <= len(title) <= 160 or not time(7) <= start < end <= time(23):
            raise ValueError('Invalid title or time in AI plan.')
        duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        if not 30 <= duration <= 120:
            raise ValueError('Session duration must be 30–120 minutes.')
        if any(d == day and a < end and b > start for d, a, b in busy):
            raise ValueError('AI plan contains overlapping sessions.')
        busy.append((day, start, end))
        proposals.append({'title': title, 'subject_id': subject_id,
                          'session_date': day, 'start_time': start, 'end_time': end,
                          'description': 'Suggested by AI; confirmed by the user.',
                          'status': 'planned'})
    return proposals


def serialize_plan(proposals):
    return [{'title': x['title'], 'subject_id': x['subject_id'],
             'date': x['session_date'].isoformat(), 'start_time': x['start_time'].strftime('%H:%M'),
             'end_time': x['end_time'].strftime('%H:%M')} for x in proposals]


def repair_ai_plan_timing(raw, *, today, days, existing):
    """Repair model-generated durations and collisions before strict validation.

    Only time fields are changed. Subject IDs, titles and dates are never
    silently replaced, so the existing ownership/date validator remains final.
    Raises ValueError when a safe slot cannot be found.
    """
    from datetime import datetime
    try:
        content = raw.strip()
        if content.startswith('```'):
            lines = content.splitlines()
            content = '\n'.join(lines[1:-1]).strip()
        parsed = json.loads(content)
        entries = parsed.get('sessions') if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list) or not 1 <= len(entries) <= 8:
            return raw  # Let the strict validator report malformed plans.
    except (ValueError, TypeError, AttributeError):
        return raw

    busy = [(x.session_date, x.start_time.hour * 60 + x.start_time.minute,
             x.end_time.hour * 60 + x.end_time.minute)
            for x in existing if x.status != 'cancelled']
    repaired = []
    for entry in entries:
        if not isinstance(entry, dict):
            return raw
        try:
            day = date.fromisoformat(entry['date'])
            start = time.fromisoformat(entry['start_time'])
            end = time.fromisoformat(entry['end_time'])
        except (ValueError, TypeError, KeyError, AttributeError):
            return raw
        if not today <= day < today + timedelta(days=days):
            return raw
        if start.second or start.microsecond or end.second or end.microsecond:
            return raw
        original_start = start.hour * 60 + start.minute
        original_end = end.hour * 60 + end.minute
        duration = original_end - original_start
        if duration < 30 or duration > 120:
            duration = 60
        # Preserve a valid proposed start when possible. Otherwise look for
        # the nearest free 30-minute slot, never leaving 07:00..23:00.
        candidates = [original_start] + list(range(7 * 60, 23 * 60 - duration + 1, 30))
        candidates = sorted(set(candidates), key=lambda minute: (abs(minute - original_start), minute))
        slot = next((minute for minute in candidates
                     if 7 * 60 <= minute and minute + duration <= 23 * 60
                     and all(d != day or minute + duration <= a or minute >= b
                             for d, a, b in busy)), None)
        if slot is None:
            raise ValueError('No free time slot is available for the AI plan. Try another period.')
        fixed = dict(entry)
        fixed['start_time'] = f'{slot // 60:02d}:{slot % 60:02d}'
        finish = slot + duration
        fixed['end_time'] = f'{finish // 60:02d}:{finish % 60:02d}'
        repaired.append(fixed)
        busy.append((day, slot, finish))
    return json.dumps({'sessions': repaired}, ensure_ascii=False)
