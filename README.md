# AI Study Planner — ST2 2026

Flask MVC уеб приложение за предмети, задачи, изпити и учебен график.
<<<<<<< HEAD
Текущ етап: **Седмица 4 / Стъпка 3 (финална)**. AI заявките ще се реализират през Седмица 5.
=======
Текущ етап: **Седмица 4 / Стъпка 3**.
>>>>>>> e623202 (week4: preperation for AI integration)

## Инсталация (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

Отвори http://127.0.0.1:5000 и създай акаунт.

## Тестове

```powershell
python -m pytest -q
```

Тестовете използват отделна временна SQLite база чрез `tests/conftest.py`; не променят личната ти база.

## Архитектура и шаблони

- **MVC**: `app/models/`, `app/controllers/`, `app/templates/`.
- **Singleton**: `app/patterns/app_settings.py` — настройки.
- **Repository**: `app/repositories/` — изолирани заявки и CRUD за текущия потребител.
- **Strategy**: `app/services/study_planning.py` — два начина за планиране.
- **AI интерфейс за Седмица 5**: `app/services/ai_gateway.py`; по подразбиране е изключен.

## Функционалности

Регистрация/вход/изход, предмети, задачи, изпити, учебни сесии, седмичен график,
генериране на план без LLM, Dashboard статистика, филтриране и сортиране.

## Сигурност

- Паролите се хешират с Werkzeug; не се пазят като обикновен текст.
- Формите за промени използват CSRF токени.
- Данните се филтрират по текущия потребител.
- Сесиите използват HttpOnly и SameSite=Lax cookies; има базови HTTP security headers.
- В production настрой `SECRET_KEY` със силна случайна стойност и HTTPS.
- Не качвай `.env`, `instance/`, `*.db` или реални потребителски данни в GitHub.
- При публично разполагане добави rate limiting, HTTPS и миграционен инструмент.

## База данни

По подразбиране SQLite: `instance/study_planner.db` (създава се при стартиране).
<<<<<<< HEAD
За тестовете се използват временни файлове. Съществуващата база **не е включена в архива**.

## Git

Публично репозитори: `ST2-2026-Team-X-AIStudyPlanner` (замени X с номера на екипа).
=======
За тестовете се използват временни файлове. Съществуващата база **не е включена в архива за момента**.

## Git

Публично репозитори: `ST2-2026-Team-1-AIStudyPlanner`
>>>>>>> e623202 (week4: preperation for AI integration)
