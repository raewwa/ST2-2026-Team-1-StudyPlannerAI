# AI Study Planner — ST2 2026

Flask MVC приложение за управление на предмети, задачи, изпити, учебни сесии и персонализирани AI планове.

## Инсталация (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -q
python run.py
```

Отвори `http://127.0.0.1:5000`. При първо стартиране SQLite таблиците се създават автоматично.
По подразбиране базата е `instance/study_planner.db`. **Запази папката `instance/` при обновяване на проекта.**

## Конфигурация

Редактирай `.env` (не го качвай в GitHub). За случаен `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

За AI инсталирай [Ollama](https://ollama.com/download/windows), след това:

```powershell
ollama pull llama3.2
ollama list
```

В `.env` настрой `AI_PROVIDER=ollama`, `OLLAMA_MODEL=llama3.2` и
`OLLAMA_BASE_URL=http://127.0.0.1:11434`. Ollama трябва да работи при генериране.
При `AI_PROVIDER=disabled` обикновените CRUD функции остават достъпни.

## Основни функции

- Регистрация, вход, изход, сесии и CSRF защита.
- CRUD за предмети, задачи, изпити и учебни сесии с проверки за собственост.
- Dashboard със статистика, филтри и сортиране.
- Седмичен график и детерминистични стратегии за планиране.
- AI съвети и AI учебен план за 7 или 14 дни.
- Преглед и **изрично потвърждение** преди AI сесиите да бъдат записани.

## Архитектура и Design Patterns

- **MVC:** `app/models/`, `app/controllers/`, `app/templates/`.
- **Singleton:** `app/patterns/app_settings.py` — общи настройки.
- **Repository:** `app/repositories/` — операции с потребителските данни.
- **Strategy:** `app/services/study_planning.py` — избор на алгоритъм за планиране.
- **Factory + Adapter:** `app/services/ai_gateway.py` — избор на AI provider и Ollama HTTP адаптер.

## AI сигурност и ограничения

AI получава само данните на текущия потребител, нужни за планиране. Изходът на модела
се счита за недоверен: проверяват се JSON форматът, предметите, датите, часовете,
продължителността и конфликтите. При запис проверките се изпълняват отново.
Не изпращай лични тайни в заглавията на задачи и предмети. Моделът може да
генерира неточни предложения; потребителят трябва да ги прегледа.

## Тестове

```powershell
python -m pytest -q
```

Тестовете използват временна SQLite база и mock AI отговори; не изискват Ollama.
Тестовете от Седмица 5, Стъпка 3 са в `tests/test_week5_step3.py`.

## Представяне на проекта

1. Регистрация/вход и потребителска изолация.
2. Добавяне на предмет, задача и изпит; филтри и Dashboard.
3. Създаване на учебна сесия и демонстрация на Strategy алгоритмите.
4. Стартиране на Ollama, AI съвети и генериране на AI план.
5. Преглед, потвърждение и проверка на записаните сесии в графика.
6. `python -m pytest -q` и показване на структурата MVC/Design Patterns.

> Ако Ollama не е наличен при демонстрацията, представи останалите функции и
> покажи mock AI интеграционните тестове; не представяй това като реална AI заявка.
