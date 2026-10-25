"""Week 3 / Step 3: Repository Pattern owner isolation and persistence."""
from datetime import date, time
import pytest
from app import create_app, db
from app.models.user import User
from app.repositories.subject_repository import SubjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.study_session_repository import StudySessionRepository


@pytest.fixture
def repositories(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'repository-test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "repo.db"}'})
    with app.app_context():
        a = User(username='owner_a', email='owner_a@example.com')
        b = User(username='owner_b', email='owner_b@example.com')
        a.set_password('password123')
        b.set_password('password123')
        db.session.add_all([a, b])
        db.session.commit()
        yield a.id, b.id
        db.session.remove()
        db.engine.dispose()


def test_subject_repository_owner_scope(repositories):
    owner, other = repositories
    own = SubjectRepository(owner)
    foreign = SubjectRepository(other)
    item = own.add(name='Математика', semester=1)
    assert own.count() == 1
    assert foreign.count() == 0
    assert foreign.exists(item.id) is False
    with pytest.raises(Exception) as error:
        foreign.get_or_404(item.id)
    assert getattr(error.value, 'code', None) == 404
    with pytest.raises(ValueError):
        foreign.update(item, name='Чужд предмет')
    with pytest.raises(ValueError):
        foreign.delete(item)
    own.update(item, name='Алгебра')
    assert own.ordered()[0].name == 'Алгебра'
    own.delete(item)
    assert own.count() == 0


def test_task_and_exam_repositories(repositories):
    owner, other = repositories
    subject = SubjectRepository(owner).add(name='Физика')
    tasks = TaskRepository(owner)
    task = tasks.add(title='Преговор', priority='high', status='pending', subject_id=subject.id)
    assert len(tasks.filtered({'priority': 'high'})) == 1
    assert TaskRepository(other).filtered() == []
    tasks.update(task, status='completed')
    assert len(tasks.filtered({'status': 'completed'})) == 1
    exams = ExamRepository(owner)
    exam = exams.add(title='Изпит', subject_id=subject.id, exam_date=date(2026, 12, 15),
                     exam_time=time(10, 0), status='upcoming')
    assert exams.ordered()[0].id == exam.id
    assert ExamRepository(other).ordered() == []
    exams.delete(exam)
    tasks.delete(task)


def test_study_session_repository_overlap_and_week(repositories):
    owner, other = repositories
    subject = SubjectRepository(owner).add(name='История')
    sessions = StudySessionRepository(owner)
    item = sessions.add(title='Преговор', subject_id=subject.id, session_date=date(2026, 12, 14),
                        start_time=time(9), end_time=time(10), status='planned')
    assert sessions.overlaps(date(2026, 12, 14), time(9, 30), time(10, 30))
    assert not sessions.overlaps(date(2026, 12, 14), time(10), time(11))
    assert not sessions.overlaps(date(2026, 12, 14), time(9), time(10), exclude_id=item.id)
    assert len(sessions.in_week(date(2026, 12, 14), date(2026, 12, 20))) == 1
    assert StudySessionRepository(other).in_week(date(2026, 12, 14), date(2026, 12, 20)) == []
    sessions.delete(item)


def test_repository_requires_valid_owner(repositories):
    for invalid in (None, 0, -1, '1'):
        with pytest.raises(ValueError):
            SubjectRepository(invalid)
