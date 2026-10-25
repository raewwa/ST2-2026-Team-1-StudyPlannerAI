"""HTTP controllers: subject INSERT and filtered SELECT (week 1 complete)."""
import hmac
import secrets
from datetime import date, time, timedelta
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
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
        errors['name'] = 'Името на предмета е задължително.'
    elif len(name) > 120:
        errors['name'] = 'Името не може да надвишава 120 символа.'
    if len(description) > 1000:
        errors['description'] = 'Описанието не може да надвишава 1000 символа.'
    semester = None
    if semester_raw:
        try:
            semester = int(semester_raw)
            if str(semester) != semester_raw or not 1 <= semester <= 12:
                raise ValueError
        except ValueError:
            errors['semester'] = 'Семестърът трябва да е цяло число между 1 и 12.'
    return {'name': name, 'description': description, 'semester': semester}, errors


@main_bp.get('/')
@login_required
def dashboard():
    task_query = TaskRepository(current_user.id).query()
    return render_template('dashboard.html', subject_count=SubjectRepository(current_user.id).count(),
                           task_count=task_query.count(),
                           pending_count=task_query.filter(Task.status != 'completed').count(),
                           completed_count=task_query.filter_by(status='completed').count())


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
        errors['search'] = f'Търсенето не може да надвишава {settings.max_search_length} символа.'
    semester = None
    if semester_raw:
        try:
            semester = int(semester_raw)
            if str(semester) != semester_raw or not settings.min_semester <= semester <= settings.max_semester:
                raise ValueError
        except ValueError:
            errors['filter_semester'] = 'Избери валиден семестър от 1 до 12.'
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
            return 'Невалиден CSRF токен. Презаредете страницата.', 400
        values, errors = validate_subject(request.form)
        if errors:
            return render_template('subjects.html', subjects=filtered, total_count=SubjectRepository(current_user.id).count(),
                                   filters=filters, filter_errors=filter_errors, values=request.form, errors=errors), 422
        try:
            SubjectRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Възникна проблем при записването. Опитайте отново.', 'danger')
            return redirect(url_for('main.subjects'))
        flash('Предметът беше добавен успешно.', 'success')
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
        errors['title'] = 'Заглавието трябва да е между 1 и 160 символа.'
    if len(description) > 2000:
        errors['description'] = 'Описанието не може да надвишава 2000 символа.'
    if priority not in ('low', 'medium', 'high'):
        errors['priority'] = 'Изберете валиден приоритет.'
    if status not in ('pending', 'in_progress', 'completed'):
        errors['status'] = 'Изберете валиден статус.'
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
            if due_date.isoformat() != due_raw:
                raise ValueError
        except ValueError:
            errors['due_date'] = 'Въведете валидна дата.'
    subject_id = None
    if subject_raw:
        try:
            subject_id = int(subject_raw)
            if str(subject_id) != subject_raw or subject_id < 1:
                raise ValueError
        except ValueError:
            errors['subject_id'] = 'Изберете валиден предмет.'
        else:
            if not SubjectRepository(current_user.id).exists(subject_id):
                errors['subject_id'] = 'Предметът не принадлежи на вашия профил.'
    return dict(title=title, description=description, due_date=due_date,
                priority=priority, status=status, subject_id=subject_id), errors


@main_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """Week 2 step 4: user-scoped CRUD and filtering."""
    subjects = SubjectRepository(current_user.id).ordered()
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_task(request.form)
        if errors:
            existing, filters, filter_errors = user_tasks_with_filters(request.args)
            return render_template('tasks.html', tasks=existing, subjects=subjects,
                                   errors=errors, values=request.form, filters=filters, filter_errors=filter_errors), 422
        try:
            TaskRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Задачата не можа да бъде записана.', 'danger')
            return redirect(url_for('main.tasks'))
        flash('Задачата е добавена успешно.', 'success')
        return redirect(url_for('main.tasks'))
    existing, filters, filter_errors = user_tasks_with_filters(request.args)
    return render_template('tasks.html', tasks=existing, subjects=subjects, errors={}, values={},
                           filters=filters, filter_errors=filter_errors)




def task_filter_values(args):
    """Validate optional GET filters; return values and field errors."""
    values = {key: args.get(key, '').strip() for key in ('status', 'priority', 'subject_id')}
    errors = {}
    if values['status'] and values['status'] not in ('pending', 'in_progress', 'completed'):
        errors['status'] = 'Невалиден статус.'
    if values['priority'] and values['priority'] not in ('low', 'medium', 'high'):
        errors['priority'] = 'Невалиден приоритет.'
    if values['subject_id']:
        try:
            subject_id = int(values['subject_id'])
            if str(subject_id) != values['subject_id'] or subject_id < 1:
                raise ValueError
        except ValueError:
            errors['subject_id'] = 'Невалиден предмет.'
        else:
            if not SubjectRepository(current_user.id).exists(subject_id):
                errors['subject_id'] = 'Невалиден предмет.'
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
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_task(request.form)
        if errors:
            return render_template('task_edit.html', task=task, subjects=subjects, values=request.form, errors=errors), 422
        try:
            TaskRepository(current_user.id).update(task, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Промените не можаха да бъдат запазени.', 'danger')
            return redirect(url_for('main.edit_task', task_id=task_id))
        flash('Задачата е обновена.', 'success')
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
        return 'Невалиден CSRF токен.', 400
    try:
        TaskRepository(current_user.id).delete(task)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Задачата не можа да бъде изтрита.', 'danger')
        return redirect(url_for('main.tasks'))
    flash('Задачата е изтрита.', 'success')
    return redirect(url_for('main.tasks'))


@main_bp.post('/tasks/<int:task_id>/toggle')
@login_required
def toggle_task(task_id):
    task = TaskRepository(current_user.id).get_or_404(task_id)
    if not check_csrf():
        return 'Невалиден CSRF токен.', 400
    task.status = 'pending' if task.status == 'completed' else 'completed'
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('Статусът не можа да бъде променен.', 'danger')
        return redirect(url_for('main.tasks'))
    flash('Статусът е променен.', 'success')
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
        errors['title'] = 'Заглавието трябва да е между 1 и 160 символа.'
    if len(description) > 2000:
        errors['description'] = 'Описанието не може да надвишава 2000 символа.'
    if len(location) > 160:
        errors['location'] = 'Мястото не може да надвишава 160 символа.'
    if status not in ('upcoming', 'completed', 'cancelled'):
        errors['status'] = 'Невалиден статус.'
    exam_date = None
    try:
        exam_date = date.fromisoformat(raw_date)
        if exam_date.isoformat() != raw_date:
            raise ValueError
    except ValueError:
        errors['exam_date'] = 'Въведете валидна дата.'
    exam_time = None
    try:
        exam_time = time.fromisoformat(raw_time)
        if exam_time.strftime('%H:%M') != raw_time:
            raise ValueError
    except ValueError:
        errors['exam_time'] = 'Въведете валиден час (ЧЧ:ММ).'
    subject_id = None
    try:
        subject_id = int(raw_subject)
        if str(subject_id) != raw_subject or subject_id < 1:
            raise ValueError
    except ValueError:
        errors['subject_id'] = 'Изберете предмет.'
    else:
        if not SubjectRepository(current_user.id).exists(subject_id):
            errors['subject_id'] = 'Избраният предмет не принадлежи на профила.'
    return dict(title=title, description=description, location=location,
                exam_date=exam_date, exam_time=exam_time, subject_id=subject_id,
                status=status), errors


def exam_subjects():
    return SubjectRepository(current_user.id).ordered()


@main_bp.route('/exams', methods=['GET', 'POST'])
@login_required
def exams():
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_exam(request.form)
        if errors:
            items = ExamRepository(current_user.id).ordered()
            return render_template('exams.html', exams=items, subjects=exam_subjects(), values=request.form, errors=errors), 422
        try:
            ExamRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Изпитът не можа да бъде записан.', 'danger')
            return redirect(url_for('main.exams'))
        flash('Изпитът е добавен успешно.', 'success')
        return redirect(url_for('main.exams'))
    items = ExamRepository(current_user.id).ordered()
    return render_template('exams.html', exams=items, subjects=exam_subjects(), values={}, errors={})


@main_bp.route('/exams/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_exam(exam_id):
    exam = ExamRepository(current_user.id).get_or_404(exam_id)
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_exam(request.form)
        if errors:
            return render_template('exam_edit.html', exam=exam, subjects=exam_subjects(), values=request.form, errors=errors), 422
        try:
            ExamRepository(current_user.id).update(exam, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Промените не можаха да бъдат запазени.', 'danger')
            return redirect(url_for('main.edit_exam', exam_id=exam_id))
        flash('Изпитът е обновен.', 'success')
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
        return 'Невалиден CSRF токен.', 400
    try:
        ExamRepository(current_user.id).delete(exam)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Изпитът не можа да бъде изтрит.', 'danger')
        return redirect(url_for('main.exams'))
    flash('Изпитът е изтрит.', 'success')
    return redirect(url_for('main.exams'))




def validate_study_session(form, exclude_id=None):
    """Server validation: owner-scoped subject and overlapping intervals."""
    title = form.get('title', '').strip()
    description = form.get('description', '').strip()
    status = form.get('status', 'planned')
    errors = {}
    if not 1 <= len(title) <= 160:
        errors['title'] = 'Заглавието трябва да е между 1 и 160 символа.'
    if len(description) > 2000:
        errors['description'] = 'Описанието не може да надвишава 2000 символа.'
    if status not in ('planned', 'completed', 'cancelled'):
        errors['status'] = 'Невалиден статус.'
    raw_date = form.get('session_date', '').strip()
    session_date = None
    try:
        session_date = date.fromisoformat(raw_date)
        if session_date.isoformat() != raw_date:
            raise ValueError
    except ValueError:
        errors['session_date'] = 'Въведете валидна дата.'
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
            errors[field] = 'Въведете валиден час (ЧЧ:ММ).'
    start_time, end_time = times['start_time'], times['end_time']
    if start_time and end_time and start_time >= end_time:
        errors['end_time'] = 'Крайният час трябва да е след началния.'
    raw_subject = form.get('subject_id', '').strip()
    subject_id = None
    try:
        subject_id = int(raw_subject)
        if str(subject_id) != raw_subject or subject_id < 1:
            raise ValueError
    except ValueError:
        errors['subject_id'] = 'Изберете валиден предмет.'
    else:
        if not SubjectRepository(current_user.id).exists(subject_id):
            errors['subject_id'] = 'Предметът не принадлежи на вашия профил.'
    if session_date and start_time and end_time and start_time < end_time and status != 'cancelled':
        # Adjacent sessions are allowed: [09:00,10:00) and [10:00,11:00).
        if StudySessionRepository(current_user.id).overlaps(
                session_date, start_time, end_time, exclude_id=exclude_id):
            errors['start_time'] = 'Има друга учебна сесия в този интервал.'
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
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_study_session(request.form)
        if errors:
            return render_schedule(monday, sunday, subjects, request.form, errors), 422
        try:
            StudySessionRepository(current_user.id).add(**values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Учебната сесия не можа да бъде записана.', 'danger')
            return redirect(url_for('main.schedule'))
        flash('Учебната сесия е добавена.', 'success')
        return redirect(url_for('main.schedule', week=values['session_date'].isoformat()))
    return render_schedule(monday, sunday, subjects, {}, {})


def render_schedule(monday, sunday, subjects, values, errors):
    items = StudySessionRepository(current_user.id).in_week(monday, sunday)
    days = [(monday + timedelta(days=i), []) for i in range(7)]
    for item in items:
        days[(item.session_date - monday).days][1].append(item)
    return render_template('schedule.html', days=days, subjects=subjects, values=values,
                           errors=errors, monday=monday, sunday=sunday,
                           previous_week=(monday - timedelta(days=7)).isoformat(),
                           next_week=(monday + timedelta(days=7)).isoformat())


@main_bp.route('/schedule/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_study_session(session_id):
    item = StudySessionRepository(current_user.id).get_or_404(session_id)
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_study_session(request.form, exclude_id=item.id)
        if errors:
            return render_template('study_session_edit.html', item=item, subjects=exam_subjects(),
                                   values=request.form, errors=errors), 422
        try:
            StudySessionRepository(current_user.id).update(item, **values)
        except SQLAlchemyError:
            db.session.rollback()
            flash('Промените не можаха да бъдат записани.', 'danger')
            return redirect(url_for('main.edit_study_session', session_id=item.id))
        flash('Учебната сесия е обновена.', 'success')
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
        return 'Невалиден CSRF токен.', 400
    week = item.session_date.isoformat()
    try:
        StudySessionRepository(current_user.id).delete(item)
    except SQLAlchemyError:
        db.session.rollback()
        flash('Учебната сесия не можа да бъде изтрита.', 'danger')
        return redirect(url_for('main.schedule', week=week))
    flash('Учебната сесия е изтрита.', 'success')
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
        errors['username'] = 'Потребителското име трябва да е между 3 и 80 символа.'
    if not 5 <= len(email) <= 255 or '@' not in email or email.startswith('@') or '.' not in email.rsplit('@', 1)[-1]:
        errors['email'] = 'Въведете валиден email адрес.'
    if len(password) < 8 or len(password) > 128:
        errors['password'] = 'Паролата трябва да е между 8 и 128 символа.'
    if password != confirm:
        errors['confirm_password'] = 'Паролите не съвпадат.'
    if db.session.query(User.id).filter(func.lower(User.username) == username.lower()).first():
        errors['username'] = 'Това потребителско име вече се използва.'
    if db.session.query(User.id).filter(func.lower(User.email) == email).first():
        errors['email'] = 'Този email вече е регистриран.'
    return username, email, password, errors


@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'GET':
        return render_template('register.html', errors={}, values={})
    if not check_csrf():
        return 'Невалиден CSRF токен.', 400
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
        return render_template('register.html', errors={'email': 'Потребителското име или email вече съществува.'}, values=request.form), 422
    login_user(user)
    flash('Регистрацията е успешна. Добре дошли!', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'GET':
        return render_template('login.html', error=None, email='')
    if not check_csrf():
        return 'Невалиден CSRF токен.', 400
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = db.session.query(User).filter(func.lower(User.email) == email).first()
    if not user or not user.check_password(password):
        return render_template('login.html', error='Невалиден email или парола.', email=email), 401
    login_user(user)
    flash('Успешен вход.', 'success')
    # Fixed destination prevents open redirects through untrusted next URLs.
    return redirect(url_for('main.dashboard'))


@main_bp.post('/logout')
@login_required
def logout():
    if not check_csrf():
        return 'Невалиден CSRF токен.', 400
    logout_user()
    flash('Излязохте успешно.', 'info')
    return redirect(url_for('main.login'))


@main_bp.route('/schedule/plan', methods=['GET', 'POST'])
@login_required
def plan_study():
    """Preview and optionally save suggestions; all inputs are user-scoped."""
    key = request.values.get('strategy', 'exam')
    if key not in STRATEGIES:
        return 'Невалидна стратегия.', 422
    if request.method == 'POST' and not check_csrf():
        return 'Невалиден CSRF токен.', 400
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
            flash('Няма свободни предложения за запис.', 'info')
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
            flash('Неуспешно записване на предложенията.', 'danger')
            return redirect(url_for('main.plan_study', strategy=key))
        flash('Учебните сесии са добавени към графика.', 'success')
        return redirect(url_for('main.schedule', week=today.isoformat()))
    return render_template('study_plan.html', proposals=proposals,
                           strategies=STRATEGIES, selected=key)
