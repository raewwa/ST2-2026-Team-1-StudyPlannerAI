"""HTTP controllers: subject INSERT and filtered SELECT (week 1 complete)."""
import hmac
import secrets
from datetime import date
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models.subject import Subject
from app.models.task import Task
from app.patterns.app_settings import AppSettings

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
    task_query = db.session.query(Task).filter_by(user_id=current_user.id)
    return render_template('dashboard.html', subject_count=owned_subjects_query().count(),
                           task_count=task_query.count(),
                           pending_count=task_query.filter(Task.status != 'completed').count(),
                           completed_count=task_query.filter_by(status='completed').count())


def owned_subjects_query():
    """Only return subjects belonging to the authenticated account."""
    return db.session.query(Subject).filter(Subject.user_id == current_user.id)


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
            return render_template('subjects.html', subjects=filtered, total_count=owned_subjects_query().count(),
                                   filters=filters, filter_errors=filter_errors, values=request.form, errors=errors), 422
        subject = Subject(**values, user_id=current_user.id)
        try:
            db.session.add(subject)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('Възникна проблем при записването. Опитайте отново.', 'danger')
            return redirect(url_for('main.subjects'))
        flash('Предметът беше добавен успешно.', 'success')
        return redirect(url_for('main.subjects'))
    return render_template('subjects.html', subjects=filtered, total_count=owned_subjects_query().count(),
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
            if db.session.query(Subject.id).filter_by(id=subject_id, user_id=current_user.id).first() is None:
                errors['subject_id'] = 'Предметът не принадлежи на вашия профил.'
    return dict(title=title, description=description, due_date=due_date,
                priority=priority, status=status, subject_id=subject_id), errors


@main_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    """Week 2 step 4: user-scoped CRUD and filtering."""
    subjects = db.session.query(Subject).filter_by(user_id=current_user.id).order_by(Subject.name).all()
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_task(request.form)
        if errors:
            existing, filters, filter_errors = user_tasks_with_filters(request.args)
            return render_template('tasks.html', tasks=existing, subjects=subjects,
                                   errors=errors, values=request.form, filters=filters, filter_errors=filter_errors), 422
        try:
            db.session.add(Task(**values, user_id=current_user.id))
            db.session.commit()
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
            if db.session.query(Subject.id).filter_by(id=subject_id, user_id=current_user.id).first() is None:
                errors['subject_id'] = 'Невалиден предмет.'
    return values, errors


def user_tasks_with_filters(args):
    filters, errors = task_filter_values(args)
    query = db.session.query(Task).filter_by(user_id=current_user.id)
    if errors:
        query = query.filter(db.false())
    else:
        for field in ('status', 'priority', 'subject_id'):
            if filters[field]:
                query = query.filter(getattr(Task, field) == filters[field])
    return query.order_by(Task.id.desc()).all(), filters, errors


@main_bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = db.session.query(Task).filter_by(id=task_id, user_id=current_user.id).first_or_404()
    subjects = db.session.query(Subject).filter_by(user_id=current_user.id).order_by(Subject.name).all()
    if request.method == 'POST':
        if not check_csrf():
            return 'Невалиден CSRF токен.', 400
        values, errors = validate_task(request.form)
        if errors:
            return render_template('task_edit.html', task=task, subjects=subjects, values=request.form, errors=errors), 422
        for key, value in values.items():
            setattr(task, key, value)
        try:
            db.session.commit()
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
    task = db.session.query(Task).filter_by(id=task_id, user_id=current_user.id).first_or_404()
    if not check_csrf():
        return 'Невалиден CSRF токен.', 400
    try:
        db.session.delete(task)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash('Задачата не можа да бъде изтрита.', 'danger')
        return redirect(url_for('main.tasks'))
    flash('Задачата е изтрита.', 'success')
    return redirect(url_for('main.tasks'))


@main_bp.post('/tasks/<int:task_id>/toggle')
@login_required
def toggle_task(task_id):
    task = db.session.query(Task).filter_by(id=task_id, user_id=current_user.id).first_or_404()
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


@main_bp.get('/exams')
@login_required
def exams():
    return render_template('placeholder.html', title='Изпити')


@main_bp.get('/schedule')
@login_required
def schedule():
    return render_template('placeholder.html', title='Учебен график')


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
