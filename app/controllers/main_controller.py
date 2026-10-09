"""Initial routes; business logic and CRUD will be added in later milestones."""
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)


@main_bp.get('/')
def dashboard():
    return render_template('dashboard.html')


@main_bp.get('/subjects')
def subjects():
    return render_template('subjects.html')


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
