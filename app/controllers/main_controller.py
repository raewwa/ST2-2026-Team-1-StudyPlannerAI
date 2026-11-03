"""HTTP controllers: subject INSERT and filtered SELECT (week 1 complete)."""
import hmac
import json
import secrets
from datetime import date, time, timedelta
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models.subject import Subject
from app.models.task import Task
from app.models.exam import Exam
from app.models.study_session import StudySession
from app.patterns.app_settings import AppSettings
from app.repositories.subject_repository import SubjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.study_session_repository import StudySessionRepository
from app.services.study_planning import STRATEGIES, StudyPlanner
from app.services.ai_gateway import create_advice_provider, AIProviderError
from app.services.ai_planning import parse_ai_plan, serialize_plan, repair_ai_plan_timing
from app.services.ai_priority import build_study_allocations

main_bp = Blueprint('main', __name__)


def csrf_token():
    """Session-bound CSRF token for HTML forms (no external form dependency)."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


@main_bp.record_once
def register_template_helpers(state):
    state.app.jinja_env.globals['csrf_token'] = csrf_token


def validate_subject(form):
    """Server-side validation independent of browser constraints."""
    name = form.get('name', '').strip()
    description = form.get('description', '').strip()
    semester_raw = form.get('semester', '').strip()
    errors = {}
    if not name:
        errors['name'] = 'Subject name is required.'
    elif len(name) > 120:
        errors['name'] = 'Subject name must be at most 120 characters.'
    if len(description) > 1000:
        errors['description'] = 'Description must be at most 1,000 characters.'
    semester = None
    if semester_raw:
        try:
            semester = int(semester_raw)
            if str(semester) != semester_raw or not 1 <= semester <= 12:
                raise ValueError
        except ValueError:
            errors['semester'] = 'Semester must be an integer from 1 to 12.'
    return {'name': name, 'description': description, 'semester': semester}, errors


@main_bp.get('/')
@login_required
def dashboard():
    """User-scoped dashboard: all counts and events come from the database."""
    today = date.today()
    user_id = current_user.id
    task_query = TaskRepository(user_id).query()
    exam_query = ExamRepository(user_id).query()
    session_query = StudySessionRepository(user_id).query()
    task_count = task_query.count()
    completed_count = task_query.filter_by(status='completed').count()
    pending_count = task_count - completed_count
    upcoming_exams = (exam_query.filter(Exam.status == 'upcoming', Exam.exam_date >= today)
                      .order_by(Exam.exam_date, Exam.exam_time).limit(5).all())
    upcoming_tasks = (task_query.filter(Task.status != 'completed', Task.due_date >= today)
                      .order_by(Task.due_date, Task.id).limit(5).all())
    upcoming_sessions = (session_query.filter(StudySession.status == 'planned',
                                               StudySession.session_date >= today)
                         .order_by(StudySession.session_date, StudySession.start_time).limit(5).all())
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_sessions = session_query.filter(StudySession.session_date >= week_start,
                                         StudySession.session_date <= week_end,
                                         StudySession.status != 'cancelled').all()
    study_minutes = sum((item.end_time.hour * 60 + item.end_time.minute) -
                        (item.start_time.hour * 60 + item.start_time.minute)
                        for item in week_sessions)
    events = ([{'kind': 'Exam', 'title': e.title, 'when': e.exam_date,
                'time': e.exam_time, 'url': url_for('main.exams')} for e in upcoming_exams] +
              [{'kind': 'Task', 'title': t.title, 'when': t.due_date,
                'time': None, 'url': url_for('main.tasks')} for t in upcoming_tasks] +
              [{'kind': 'Study Session', 'title': x.title, 'when': x.session_date,
                'time': x.start_time, 'url': url_for('main.schedule')} for x in upcoming_sessions])
    events.sort(key=lambda event: (event['when'], event['time'] or time.min))
    return render_template('dashboard.html',
                           subject_count=SubjectRepository(user_id).count(),
                           task_count=task_count, pending_count=pending_count,
                           completed_count=completed_count,
                           completion_percent=round(completed_count * 100 / task_count) if task_count else 0,
                           upcoming_exam_count=exam_query.filter(Exam.status == 'upcoming', Exam.exam_date >= today).count(),
                           study_minutes=study_minutes, events=events[:8])


def owned_subjects_query():
    """Only return subjects belonging to the authenticated account."""
    return SubjectRepository(current_user.id).query()


def filtered_subjects(args):
    """SELECT with Filter: combine case-insensitive name and semester filters.

    Invalid GET filters produce a helpful message, not a server error.
    SQLAlchemy parameters prevent SQL injection.
    """
    settings = AppSettings()
    search = args.get('search', '').strip()
    semester_raw = args.get('semester', '').strip()
    errors = {}
    if len(search) > settings.max_search_length:
        errors['search'] = f'Search must be at most {settings.max_search_length} characters.'
    semester = None
    if semester_raw:
        try:
            semester = int(semester_raw)
            if str(semester) != semester_raw or not settings.min_semester <= semester <= settings.max_semester:
                raise ValueError
        except ValueError:
            errors['filter_semester'] = 'Select a valid semester from 1 to 12.'
    query = owned_subjects_query()
    if not errors:
        if search:
            # `contains` escapes user-entered SQL wildcard characters.
            if db.engine.dialect.name == 'sqlite':
                # Unicode-aware Bulgarian search: SQLite's built-in LOWER is ASCII-only.
                query = query.filter(func.unicode_casefold(Subject.name).contains(search.casefold(), autoescape=True))
            else:
                query = query.filter(Subject.name.icontains(search, autoescape=True))
        if semester is not None:
            query = query.filter(Subject.semester == semester)
    else:
        # Never silently return unfiltered data for malformed filters.
        query = query.filter(db.false())
    return query.order_by(Subject.id.desc()).all(), {'search': search, 'semester': semester_raw}, errors


@main_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
def subjects():
    filtered, filters, filter_errors = filtered_subjects(request.args)
    if request.method == 'POST':
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('csrf_token', '')
        if not expected or not hmac.compare_digest(expected, supplied):
            return 'Invalid CSRF token. Refresh the page.', 400
        values, errors = validate_subject(request.form)
        if errors:
            return render_template('subjects.html', subjects=filtered, total_count=SubjectRepository(current_user.id).count(),
                                   filters=filters, filter_errors=filter_errors, values=request.form, errors=errors), 422
        try:
            SubjectRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save. Please try again.', 'danger')
            return redirect(url_for('main.subjects'))
        flash('Subject added successfully.', 'success')
        return redirect(url_for('main.subjects'))
    return render_template('subjects.html', subjects=filtered, total_count=SubjectRepository(current_user.id).count(),
                           filters=filters, filter_errors=filter_errors, values={}, errors={})


def validate_task(form):
    """Backend validation; subject must be owned by the authenticated user."""
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    due_raw = form.get('due_date', '').strip()
    priority = form.get('priority', 'medium')
    status = form.get('status', 'pending')
    subject_raw = form.get('subject_id', '').strip()
    errors = {}
    if not 1 <= len(title) <= 160:
        errors['title'] = 'Title must be between 1 and 160 characters.'
    if len(description) > 2000:
        errors['description'] = 'Description must be at most 2,000 characters.'
    if priority not in ('low', 'medium', 'high'):
        errors['priority'] = 'Select a valid priority.'
    if status not in ('pending', 'in_progress', 'completed'):
        errors['status'] = 'Select a valid status.'
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
            if due_date.isoformat() != due_raw:
                raise ValueError
        except ValueError:
            errors['due_date'] = 'Enter a valid date.'
    subject_id = None
    if subject_raw:
        try:
            subject_id = int(subject_raw)
            if str(subject_id) != subject_raw or subject_id < 1:
                raise ValueError
        except ValueError:
            errors['subject_id'] = 'Select a valid subject.'
        else:
            if not SubjectRepository(current_user.id).exists(subject_id):
                errors['subject_id'] = 'This subject does not belong to your account.'
    return dict(title=title, description=description, due_date=due_date,
                priority=priority, status=status, subject_id=subject_id), errors


@main_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """Week 2 step 4: user-scoped CRUD and filtering."""
    subjects = SubjectRepository(current_user.id).ordered()
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_task(request.form)
        if errors:
            existing, filters, filter_errors = user_tasks_with_filters(request.args)
            return render_template('tasks.html', tasks=existing, subjects=subjects,
                                   errors=errors, values=request.form, filters=filters, filter_errors=filter_errors), 422
        try:
            TaskRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save the task.', 'danger')
            return redirect(url_for('main.tasks'))
        flash('Task added successfully.', 'success')
        return redirect(url_for('main.tasks'))
    existing, filters, filter_errors = user_tasks_with_filters(request.args)
    return render_template('tasks.html', tasks=existing, subjects=subjects, errors={}, values={},
                           filters=filters, filter_errors=filter_errors)




def task_filter_values(args):
    """Validate optional GET filters; return values and field errors."""
    values = {key: args.get(key, '').strip() for key in ('status', 'priority', 'subject_id', 'search', 'sort')}
    errors = {}
    if len(values['search']) > 120:
        errors['search'] = 'Search must be at most 120 characters.'
    if values['sort'] and values['sort'] not in ('newest', 'oldest', 'due_asc', 'due_desc', 'priority'):
        errors['sort'] = 'Invalid sort order.'
    if values['status'] and values['status'] not in ('pending', 'in_progress', 'completed'):
        errors['status'] = 'Invalid status.'
    if values['priority'] and values['priority'] not in ('low', 'medium', 'high'):
        errors['priority'] = 'Invalid priority.'
    if values['subject_id']:
        try:
            subject_id = int(values['subject_id'])
            if str(subject_id) != values['subject_id'] or subject_id < 1:
                raise ValueError
        except ValueError:
            errors['subject_id'] = 'Invalid subject.'
        else:
            if not SubjectRepository(current_user.id).exists(subject_id):
                errors['subject_id'] = 'Invalid subject.'
    return values, errors


def user_tasks_with_filters(args):
    filters, errors = task_filter_values(args)
    items = [] if errors else TaskRepository(current_user.id).filtered(filters)
    return items, filters, errors


@main_bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = TaskRepository(current_user.id).get_or_404(task_id)
    subjects = SubjectRepository(current_user.id).ordered()
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_task(request.form)
        if errors:
            return render_template('task_edit.html', task=task, subjects=subjects, values=request.form, errors=errors), 422
        try:
            TaskRepository(current_user.id).update(task, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save changes.', 'danger')
            return redirect(url_for('main.edit_task', task_id=task_id))
        flash('Task updated.', 'success')
        return redirect(url_for('main.tasks'))
    values = {'title': task.title, 'description': task.description or '',
              'due_date': task.due_date.isoformat() if task.due_date else '',
              'priority': task.priority, 'status': task.status,
              'subject_id': str(task.subject_id) if task.subject_id else ''}
    return render_template('task_edit.html', task=task, subjects=subjects, values=values, errors={})


@main_bp.post('/tasks/<int:task_id>/delete')
@login_required
def delete_task(task_id):
    task = TaskRepository(current_user.id).get_or_404(task_id)
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    try:
        TaskRepository(current_user.id).delete(task)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Could not delete the task.', 'danger')
        return redirect(url_for('main.tasks'))
    flash('Task deleted.', 'success')
    return redirect(url_for('main.tasks'))


@main_bp.post('/tasks/<int:task_id>/toggle')
@login_required
def toggle_task(task_id):
    task = TaskRepository(current_user.id).get_or_404(task_id)
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    task.status = 'pending' if task.status == 'completed' else 'completed'
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('Could not change status.', 'danger')
        return redirect(url_for('main.tasks'))
    flash('Status updated.', 'success')
    return redirect(url_for('main.tasks'))


def validate_exam(form):
    """Backend validation, including ownership of the referenced subject."""
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    location = form.get('location', '').strip()
    raw_date = form.get('exam_date', '').strip()
    raw_time = form.get('exam_time', '').strip()
    raw_subject = form.get('subject_id', '').strip()
    status = form.get('status', 'upcoming')
    errors = {}
    if not 1 <= len(title) <= 160:
        errors['title'] = 'Title must be between 1 and 160 characters.'
    if len(description) > 2000:
        errors['description'] = 'Description must be at most 2,000 characters.'
    if len(location) > 160:
        errors['location'] = 'Location must be at most 160 characters.'
    if status not in ('upcoming', 'completed', 'cancelled'):
        errors['status'] = 'Invalid status.'
    exam_date = None
    try:
        exam_date = date.fromisoformat(raw_date)
        if exam_date.isoformat() != raw_date:
            raise ValueError
    except ValueError:
        errors['exam_date'] = 'Enter a valid date.'
    exam_time = None
    try:
        exam_time = time.fromisoformat(raw_time)
        if exam_time.strftime('%H:%M') != raw_time:
            raise ValueError
    except ValueError:
        errors['exam_time'] = 'Enter a valid time (HH:MM).'
    subject_id = None
    try:
        subject_id = int(raw_subject)
        if str(subject_id) != raw_subject or subject_id < 1:
            raise ValueError
    except ValueError:
        errors['subject_id'] = 'Select a subject.'
    else:
        if not SubjectRepository(current_user.id).exists(subject_id):
            errors['subject_id'] = 'The selected subject does not belong to your account.'
    return dict(title=title, description=description, location=location,
                exam_date=exam_date, exam_time=exam_time, subject_id=subject_id,
                status=status), errors


def exam_subjects():
    return SubjectRepository(current_user.id).ordered()


def filtered_exams(args):
    """Owner-scoped exam search/filter/sort; allowlist all query parameters."""
    values = {key: args.get(key, '').strip() for key in ('search', 'status', 'subject_id', 'sort')}
    errors = {}
    if len(values['search']) > 120:
        errors['search'] = 'Search must be at most 120 characters.'
    if values['status'] and values['status'] not in ('upcoming', 'completed', 'cancelled'):
        errors['status'] = 'Invalid status.'
    if values['sort'] and values['sort'] not in ('date_asc', 'date_desc', 'title'):
        errors['sort'] = 'Invalid sort order.'
    if values['subject_id']:
        try:
            sid = int(values['subject_id'])
            if sid < 1 or str(sid) != values['subject_id'] or not SubjectRepository(current_user.id).exists(sid):
                raise ValueError
        except ValueError:
            errors['subject_id'] = 'Invalid subject.'
    if errors:
        return [], values, errors
    query = ExamRepository(current_user.id).query()
    if values['search']:
        escaped = values['search'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(Exam.title.ilike(f'%{escaped}%', escape='\\'))
    if values['status']:
        query = query.filter(Exam.status == values['status'])
    if values['subject_id']:
        query = query.filter(Exam.subject_id == int(values['subject_id']))
    order = {'date_asc': (Exam.exam_date.asc(), Exam.exam_time.asc()),
             'date_desc': (Exam.exam_date.desc(), Exam.exam_time.desc()),
             'title': (Exam.title.asc(), Exam.id.asc())}
    return query.order_by(*order.get(values['sort'], order['date_asc'])).all(), values, errors


@main_bp.route('/exams', methods=['GET', 'POST'])
@login_required
def exams():
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_exam(request.form)
        if errors:
            items, filters, filter_errors = filtered_exams(request.args)
            return render_template('exams.html', exams=items, subjects=exam_subjects(), values=request.form, errors=errors, filters=filters, filter_errors=filter_errors), 422
        try:
            ExamRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save the exam.', 'danger')
            return redirect(url_for('main.exams'))
        flash('Exam added successfully.', 'success')
        return redirect(url_for('main.exams'))
    items, filters, filter_errors = filtered_exams(request.args)
    return render_template('exams.html', exams=items, subjects=exam_subjects(), values={}, errors={}, filters=filters, filter_errors=filter_errors)


@main_bp.route('/exams/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_exam(exam_id):
    exam = ExamRepository(current_user.id).get_or_404(exam_id)
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_exam(request.form)
        if errors:
            return render_template('exam_edit.html', exam=exam, subjects=exam_subjects(), values=request.form, errors=errors), 422
        try:
            ExamRepository(current_user.id).update(exam, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save changes.', 'danger')
            return redirect(url_for('main.edit_exam', exam_id=exam_id))
        flash('Exam updated.', 'success')
        return redirect(url_for('main.exams'))
    values = dict(title=exam.title, description=exam.description or '', location=exam.location or '',
                  exam_date=exam.exam_date.isoformat(), exam_time=exam.exam_time.strftime('%H:%M'),
                  subject_id=str(exam.subject_id), status=exam.status)
    return render_template('exam_edit.html', exam=exam, subjects=exam_subjects(), values=values, errors={})


@main_bp.post('/exams/<int:exam_id>/delete')
@login_required
def delete_exam(exam_id):
    exam = ExamRepository(current_user.id).get_or_404(exam_id)
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    try:
        ExamRepository(current_user.id).delete(exam)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Could not delete the exam.', 'danger')
        return redirect(url_for('main.exams'))
    flash('Exam deleted.', 'success')
    return redirect(url_for('main.exams'))



@main_bp.post('/exams/<int:exam_id>/toggle')
@login_required
def toggle_exam(exam_id):
    """Quickly complete or reopen an owned exam; CSRF-protected POST only."""
    exam = ExamRepository(current_user.id).get_or_404(exam_id)
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    exam.status = 'upcoming' if exam.status == 'completed' else 'completed'
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('Could not change exam status.', 'danger')
        return redirect(url_for('main.exams'))
    flash('Exam status updated.', 'success')
    return redirect(url_for('main.exams'))



def validate_study_session(form, exclude_id=None):
    """Server validation: owner-scoped subject and overlapping intervals."""
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    status = form.get('status', 'planned')
    errors = {}
    if not 1 <= len(title) <= 160:
        errors['title'] = 'Title must be between 1 and 160 characters.'
    if len(description) > 2000:
        errors['description'] = 'Description must be at most 2,000 characters.'
    if status not in ('planned', 'completed', 'cancelled'):
        errors['status'] = 'Invalid status.'
    raw_date = form.get('session_date', '').strip()
    session_date = None
    try:
        session_date = date.fromisoformat(raw_date)
        if session_date.isoformat() != raw_date:
            raise ValueError
    except ValueError:
        errors['session_date'] = 'Enter a valid date.'
    times = {}
    for field in ('start_time', 'end_time'):
        raw = form.get(field, '').strip()
        try:
            parsed = time.fromisoformat(raw)
            if parsed.strftime('%H:%M') != raw:
                raise ValueError
            times[field] = parsed
        except ValueError:
            times[field] = None
            errors[field] = 'Enter a valid time (HH:MM).'
    start_time, end_time = times['start_time'], times['end_time']
    if start_time and end_time and start_time >= end_time:
        errors['end_time'] = 'End time must be after start time.'
    raw_subject = form.get('subject_id', '').strip()
    subject_id = None
    try:
        subject_id = int(raw_subject)
        if str(subject_id) != raw_subject or subject_id < 1:
            raise ValueError
    except ValueError:
        errors['subject_id'] = 'Select a valid subject.'
    else:
        if not SubjectRepository(current_user.id).exists(subject_id):
            errors['subject_id'] = 'This subject does not belong to your account.'
    if session_date and start_time and end_time and start_time < end_time and status != 'cancelled':
        # Adjacent sessions are allowed: [09:00,10:00) and [10:00,11:00).
        if StudySessionRepository(current_user.id).overlaps(
                session_date, start_time, end_time, exclude_id=exclude_id):
            errors['start_time'] = 'Another study session overlaps this time.'
    return dict(title=title, description=description, session_date=session_date,
                start_time=start_time, end_time=end_time, status=status,
                subject_id=subject_id), errors


def schedule_week(args):
    """Return Monday–Sunday range, with an optional ISO date in the query string."""
    raw = args.get('week', '').strip()
    try:
        chosen = date.fromisoformat(raw) if raw else date.today()
        if raw and chosen.isoformat() != raw:
            raise ValueError
    except ValueError:
        chosen = date.today()
    monday = chosen - timedelta(days=chosen.weekday())
    return monday, monday + timedelta(days=6)


@main_bp.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    monday, sunday = schedule_week(request.args)
    subjects = exam_subjects()
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_study_session(request.form)
        if errors:
            return render_schedule(monday, sunday, subjects, request.form, errors), 422
        try:
            StudySessionRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save the study session.', 'danger')
            return redirect(url_for('main.schedule'))
        flash('Study session added.', 'success')
        return redirect(url_for('main.schedule', week=values['session_date'].isoformat()))
    return render_schedule(monday, sunday, subjects, {}, {})


def render_schedule(monday, sunday, subjects, values, errors):
    items = StudySessionRepository(current_user.id).in_week(monday, sunday)
    filters = {key: request.args.get(key, '').strip() for key in ('status', 'subject_id', 'sort')}
    filter_errors = {}
    if filters['status'] and filters['status'] not in ('planned', 'completed', 'cancelled'):
        filter_errors['status'] = 'Invalid status.'
    if filters['sort'] and filters['sort'] not in ('time_asc', 'time_desc'):
        filter_errors['sort'] = 'Invalid sort order.'
    if filters['subject_id']:
        try:
            sid = int(filters['subject_id'])
            if sid < 1 or str(sid) != filters['subject_id'] or not SubjectRepository(current_user.id).exists(sid):
                raise ValueError
        except ValueError:
            filter_errors['subject_id'] = 'Invalid subject.'
    if filter_errors:
        items = []
    else:
        if filters['status']:
            items = [item for item in items if item.status == filters['status']]
        if filters['subject_id']:
            items = [item for item in items if item.subject_id == int(filters['subject_id'])]
        if filters['sort'] == 'time_desc':
            items = sorted(items, key=lambda item: (item.session_date, item.start_time), reverse=True)
    days = [(monday + timedelta(days=i), []) for i in range(7)]
    for item in items:
        days[(item.session_date - monday).days][1].append(item)
    return render_template('schedule.html', days=days, subjects=subjects, values=values,
                           errors=errors, filters=filters, filter_errors=filter_errors, monday=monday, sunday=sunday,
                           previous_week=(monday - timedelta(days=7)).isoformat(),
                           next_week=(monday + timedelta(days=7)).isoformat())


@main_bp.route('/schedule/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_study_session(session_id):
    item = StudySessionRepository(current_user.id).get_or_404(session_id)
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        values, errors = validate_study_session(request.form, exclude_id=item.id)
        if errors:
            return render_template('study_session_edit.html', item=item, subjects=exam_subjects(),
                                   values=request.form, errors=errors), 422
        try:
            StudySessionRepository(current_user.id).update(item, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save changes.', 'danger')
            return redirect(url_for('main.edit_study_session', session_id=item.id))
        flash('Study session updated.', 'success')
        return redirect(url_for('main.schedule', week=item.session_date.isoformat()))
    values = dict(title=item.title, description=item.description or '',
                  session_date=item.session_date.isoformat(),
                  start_time=item.start_time.strftime('%H:%M'), end_time=item.end_time.strftime('%H:%M'),
                  subject_id=str(item.subject_id), status=item.status)
    return render_template('study_session_edit.html', item=item, subjects=exam_subjects(), values=values, errors={})


@main_bp.post('/schedule/<int:session_id>/delete')
@login_required
def delete_study_session(session_id):
    item = StudySessionRepository(current_user.id).get_or_404(session_id)
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    week = item.session_date.isoformat()
    try:
        StudySessionRepository(current_user.id).delete(item)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Could not delete the study session.', 'danger')
        return redirect(url_for('main.schedule', week=week))
    flash('Study session deleted.', 'success')
    return redirect(url_for('main.schedule', week=week))


def check_csrf():
    expected = session.get('_csrf_token', '')
    supplied = request.form.get('csrf_token', '')
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def register_errors(form):
    username = form.get('username', '').strip()
    email = form.get('email', '').strip().lower()
    password = form.get('password', '')
    confirm = form.get('confirm_password', '')
    errors = {}
    if not 3 <= len(username) <= 80:
        errors['username'] = 'Username must be between 3 and 80 characters.'
    if not 5 <= len(email) <= 255 or '@' not in email or email.startswith('@') or '.' not in email.rsplit('@', 1)[-1]:
        errors['email'] = 'Enter a valid email address.'
    if len(password) < 8 or len(password) > 128:
        errors['password'] = 'Password must be between 8 and 128 characters.'
    if password != confirm:
        errors['confirm_password'] = 'Passwords do not match.'
    if db.session.query(User.id).filter(func.lower(User.username) == username.lower()).first():
        errors['username'] = 'This username is already taken.'
    if db.session.query(User.id).filter(func.lower(User.email) == email).first():
        errors['email'] = 'This email is already registered.'
    return username, email, password, errors


@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'GET':
        return render_template('register.html', errors={}, values={})
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    username, email, password, errors = register_errors(request.form)
    if errors:
        return render_template('register.html', errors=errors, values=request.form), 422
    user = User(username=username, email=email)
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return render_template('register.html', errors={'email': 'Username or email already exists.'}, values=request.form), 422
    login_user(user)
    flash('Registration successful. Welcome!', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'GET':
        return render_template('login.html', error=None, email='')
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = db.session.query(User).filter(func.lower(User.email) == email).first()
    if not user or not user.check_password(password):
        return render_template('login.html', error='Invalid email or password.', email=email), 401
    login_user(user)
    flash('Signed in successfully.', 'success')
    # Fixed destination prevents open redirects through untrusted next URLs.
    return redirect(url_for('main.dashboard'))


@main_bp.post('/logout')
@login_required
def logout():
    if not check_csrf():
        return 'Invalid CSRF token.', 400
    logout_user()
    flash('Signed out successfully.', 'info')
    return redirect(url_for('main.login'))


@main_bp.route('/schedule/plan', methods=['GET', 'POST'])
@login_required
def plan_study():
    """Preview and optionally save suggestions; all inputs are user-scoped."""
    key = request.values.get('strategy', 'exam')
    if key not in STRATEGIES:
        return 'Invalid strategy.', 422
    if request.method == 'POST' and not check_csrf():
        return 'Invalid CSRF token.', 400
    today = date.today()
    exams = ExamRepository(current_user.id).ordered()
    tasks = TaskRepository(current_user.id).query().all()
    goals = [dict(kind='exam', title=x.title, due=x.exam_date,
                  subject_id=x.subject_id, priority=0)
             for x in exams if x.status == 'upcoming' and x.exam_date >= today]
    goals.extend(dict(kind='task', title=x.title, due=x.due_date,
                      subject_id=x.subject_id,
                      priority={'high': 3, 'medium': 2, 'low': 1}.get(x.priority, 1))
                 for x in tasks if x.status != 'completed' and x.subject_id is not None
                 and (x.due_date is None or x.due_date >= today))
    existing = StudySessionRepository(current_user.id).query().filter(
        StudySession.session_date >= today,
        StudySession.session_date <= today + timedelta(days=6)).all()
    proposals = StudyPlanner(STRATEGIES[key]).propose(goals, existing, today=today)
    if request.method == 'POST':
        if not proposals:
            flash('No available suggestions to save.', 'info')
            return redirect(url_for('main.plan_study', strategy=key))
        try:
            repo = StudySessionRepository(current_user.id)
            for proposal in proposals:
                # Recheck overlap immediately before saving each suggested slot.
                if repo.overlaps(proposal['session_date'], proposal['start_time'], proposal['end_time']):
                    continue
                repo.add(**proposal)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Could not save suggestions.', 'danger')
            return redirect(url_for('main.plan_study', strategy=key))
        flash('Study sessions added to the schedule.', 'success')
        return redirect(url_for('main.schedule', week=today.isoformat()))
    return render_template('study_plan.html', proposals=proposals,
                           strategies=STRATEGIES, selected=key)


@main_bp.route('/ai/advice', methods=['GET', 'POST'])
@login_required
def ai_advice():
    """User-scoped LLM advice. Never sends email, password hashes or other users' data."""
    advice = None
    error_message = None
    user_prompt = ''
    enabled = current_app.config.get('AI_PROVIDER', 'disabled') == 'ollama'
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        user_prompt = request.form.get('user_prompt', '').strip()
        if len(user_prompt) > 2000:
            error_message = 'Your prompt must be 2,000 characters or fewer.'
        elif not enabled:
            error_message = 'AI is disabled. Set AI_PROVIDER=ollama.'
        else:
            subjects = SubjectRepository(current_user.id).query().limit(20).all()
            tasks = TaskRepository(current_user.id).query().limit(30).all()
            exams = ExamRepository(current_user.id).query().limit(20).all()
            context = {
                'user_prompt': user_prompt,
                'subjects': [x.name[:120] for x in subjects],
                'tasks': [{'title': x.title[:160], 'priority': x.priority,
                           'status': x.status, 'due': x.due_date.isoformat() if x.due_date else None}
                          for x in tasks],
                'exams': [{'title': x.title[:160], 'date': x.exam_date.isoformat(),
                           'status': x.status} for x in exams],
            }
            try:
                advice = create_advice_provider(current_app.config).suggest(context)
            except (AIProviderError, ValueError) as exc:
                error_message = str(exc)
    return render_template('ai_advice.html', advice=advice, error_message=error_message,
                           enabled=enabled, user_prompt=user_prompt)


@main_bp.route('/ai/plan', methods=['GET', 'POST'])
@login_required
def ai_plan():
    """Preview LLM plan, then explicitly confirm; never auto-save model output."""
    enabled = current_app.config.get('AI_PROVIDER', 'disabled') == 'ollama'
    today = date.today()
    preview = None
    error_message = None
    days = 7
    subjects = SubjectRepository(current_user.id).query().order_by(Subject.name).limit(30).all()
    allowed = {x.id for x in subjects}
    if request.method == 'POST':
        if not check_csrf():
            return 'Invalid CSRF token.', 400
        try:
            days = int(request.form.get('days', '7'))
        except ValueError:
            return 'Invalid planning period.', 422
        if days not in (7, 14):
            return 'Invalid planning period.', 422
        action = request.form.get('action', 'generate')
        if action not in ('generate', 'save'):
            return 'Invalid action.', 422
        if action == 'generate':
            session.pop('ai_plan_preview', None)
            if not enabled:
                error_message = 'AI is disabled. Set AI_PROVIDER=ollama.'
            elif not subjects:
                error_message = 'Add at least one subject before generating a plan.'
            else:
                tasks = TaskRepository(current_user.id).query().limit(40).all()
                exams = ExamRepository(current_user.id).query().limit(30).all()
                existing = StudySessionRepository(current_user.id).query().filter(
                    StudySession.session_date >= today,
                    StudySession.session_date < today + timedelta(days=days)).all()
                context = {
                    'instruction': ('Return ONLY a JSON object with a sessions array containing 1 to 8 study sessions. '
                                    'Each session must have title, subject_id, date (YYYY-MM-DD), '
                                    'start_time (HH:MM), end_time (HH:MM). '
                                    'Dates must be in the requested period; times between 07:00 and 23:00; '
                                    'duration 30–120 minutes; no overlaps. '
                                    'No markdown or explanations.'),
                    'today': today.isoformat(), 'days': days,
                    'subjects': [{'id': x.id, 'name': x.name[:120]} for x in subjects],
                    'tasks': [{'title': x.title[:160], 'subject_id': x.subject_id,
                               'priority': x.priority, 'status': x.status,
                               'due': x.due_date.isoformat() if x.due_date else None} for x in tasks],
                    'exams': [{'title': x.title[:160], 'subject_id': x.subject_id,
                               'date': x.exam_date.isoformat(), 'status': x.status} for x in exams],
                    'occupied': [{'date': x.session_date.isoformat(),
                                  'start_time': x.start_time.strftime('%H:%M'),
                                  'end_time': x.end_time.strftime('%H:%M')}
                                 for x in existing if x.status != 'cancelled'],
                }
                # Explainable, deterministic workload targets: higher-priority tasks
                # and nearer exams receive a larger share of study time.
                context['study_allocations'] = build_study_allocations(context)
                try:
                    raw = create_advice_provider(current_app.config).suggest(context)
                    raw = repair_ai_plan_timing(raw, today=today, days=days, existing=existing)
                    preview = parse_ai_plan(raw, today=today, days=days,
                                            allowed_subject_ids=allowed, existing=existing)
                    session['ai_plan_preview'] = {'user_id': current_user.id,
                                                   'created': today.isoformat(),
                                                   'days': days, 'items': serialize_plan(preview)}
                except (AIProviderError, ValueError) as exc:
                    error_message = str(exc)
        else:
            if not enabled:
                session.pop('ai_plan_preview', None)
                return 'AI is disabled. Generation and saving are unavailable.', 422
            saved = session.pop('ai_plan_preview', None)
            if (not saved or saved.get('user_id') != current_user.id
                    or saved.get('created') != today.isoformat()
                    or saved.get('days') != days):
                return 'No valid AI plan to save.', 422
            existing = StudySessionRepository(current_user.id).query().filter(
                StudySession.session_date >= today,
                StudySession.session_date < today + timedelta(days=days)).all()
            try:
                preview = parse_ai_plan(json.dumps(saved['items'], ensure_ascii=False), today=today, days=days,
                                        allowed_subject_ids=allowed, existing=existing)
            except (ValueError, KeyError, TypeError):
                return 'The AI plan is no longer valid. Generate a new one.', 422
            try:
                for item in preview:
                    db.session.add(StudySession(user_id=current_user.id, **item))
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                flash('Could not save the AI plan.', 'danger')
                return redirect(url_for('main.ai_plan'))
            flash('AI study plan saved to your schedule.', 'success')
            return redirect(url_for('main.schedule', week=today.isoformat()))
    else:
        stored = session.get('ai_plan_preview')
        if stored and stored.get('user_id') == current_user.id and stored.get('created') == today.isoformat():
            days = stored.get('days', 7)
            try:
                preview = parse_ai_plan(json.dumps(stored['items'], ensure_ascii=False), today=today, days=days,
                                        allowed_subject_ids=allowed,
                                        existing=StudySessionRepository(current_user.id).query().filter(
                                            StudySession.session_date >= today,
                                            StudySession.session_date < today + timedelta(days=days)).all())
            except (ValueError, KeyError, TypeError):
                session.pop('ai_plan_preview', None)
    return render_template('ai_plan.html', enabled=enabled, days=days,
                           preview=preview, error_message=error_message)
