"""HTTP controllers: rendering, validation, and subject creation (week 1, part 2)."""
import hmac
import secrets
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import SQLAlchemyError
from app import db
from app.models.subject import Subject

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


@main_bp.route('/subjects', methods=['GET', 'POST'])
def subjects():
    if request.method == 'POST':
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('csrf_token', '')
        if not expected or not hmac.compare_digest(expected, supplied):
            return 'Невалиден CSRF токен. Презаредете страницата.', 400
        values, errors = validate_subject(request.form)
        if errors:
            return render_template('subjects.html', subjects=Subject.query.order_by(Subject.id.desc()).all(),
                                   values=request.form, errors=errors), 422
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
    return render_template('subjects.html', subjects=Subject.query.order_by(Subject.id.desc()).all(),
                           values={}, errors={})


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
