"""HTTP controllers: subject INSERT and filtered SELECT (week 1 complete)."""
import hmac
import secrets
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models.subject import Subject
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
def dashboard():
    return render_template('dashboard.html', subject_count=db.session.query(Subject).count())


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
    query = db.session.query(Subject)
    if not errors:
        if search:
            # `contains` escapes user-entered SQL wildcard characters.
            query = query.filter(Subject.name.icontains(search, autoescape=True))
        if semester is not None:
            query = query.filter(Subject.semester == semester)
    else:
        # Never silently return unfiltered data for malformed filters.
        query = query.filter(db.false())
    return query.order_by(Subject.id.desc()).all(), {'search': search, 'semester': semester_raw}, errors


@main_bp.route('/subjects', methods=['GET', 'POST'])
def subjects():
    filtered, filters, filter_errors = filtered_subjects(request.args)
    if request.method == 'POST':
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('csrf_token', '')
        if not expected or not hmac.compare_digest(expected, supplied):
            return 'Невалиден CSRF токен. Презаредете страницата.', 400
        values, errors = validate_subject(request.form)
        if errors:
            return render_template('subjects.html', subjects=filtered, total_count=db.session.query(Subject).count(),
                                   filters=filters, filter_errors=filter_errors, values=request.form, errors=errors), 422
        subject = Subject(**values)
        try:
            db.session.add(subject)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('Възникна проблем при записването. Опитайте отново.', 'danger')
            return redirect(url_for('main.subjects'))
        flash('Предметът беше добавен успешно.', 'success')
        return redirect(url_for('main.subjects'))
    return render_template('subjects.html', subjects=filtered, total_count=db.session.query(Subject).count(),
                           filters=filters, filter_errors=filter_errors, values={}, errors={})


@main_bp.get('/tasks')
def tasks():
    return render_template('placeholder.html', title='Задачи')


@main_bp.get('/exams')
def exams():
    return render_template('placeholder.html', title='Изпити')


@main_bp.get('/schedule')
def schedule():
    return render_template('placeholder.html', title='Учебен график')


@main_bp.get('/login')
def login():
    return render_template('placeholder.html', title='Вход')


@main_bp.get('/register')
def register():
    return render_template('placeholder.html', title='Регистрация')
