# Этап 0 — каркас. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пустой, но рабочий каркас: бэкенд стартует и отвечает на health-check с проверкой БД, Alembic накатывает и откатывает базовую миграцию, pytest и ruff проходят; Angular-проект собирается, тестируется, линтуется и проксирует `/api` на бэкенд.

**Architecture:** Монорепозиторий: `backend/` (FastAPI, пакет `app` со слоями из дизайна — в этом этапе только `core`, `db`, `api`) и `frontend/` (Angular CLI). Конфигурация — pydantic-settings из общего `.env` в корне репозитория. Приложение собирается фабрикой `create_app()` (без глобального экземпляра, чтобы импорт не требовал `.env`).

**Tech Stack:** Python ≥3.12 (локально 3.14), FastAPI, uvicorn, SQLAlchemy 2.x, Alembic, Pydantic v2 + pydantic-settings, httpx (зависимость под этап 1), pytest, ruff; Angular (последняя версия CLI), pnpm, angular-eslint.

**Spec:** `docs/superpowers/specs/2026-11-18-adrobot-design.md` (разделы 3.1, 6.1, 6.4, 10), правила — `CLAUDE.md` (разделы 4, 7, 8, 10).

## Global Constraints

- Секреты только в `.env` (корень репозитория); в git — только `.env.example`. Ключ API не печатается нигде (`SecretStr`).
- БД по умолчанию SQLite, строка подключения — `DATABASE_URL`; любое изменение схемы — только миграцией Alembic, откат и накат работают.
- Путь репозитория содержит пробел (`D:\0. workat\...`) — всё должно работать с такими путями.
- Бэкенд синхронный (дизайн, раздел 11).
- Angular: standalone-компоненты, signals, только `@if/@for/@switch`, TypeScript strict, pnpm. В шаблонах нет вызовов методов и геттеров (чтение сигналов `x()` — допустимо).
- Комментарии объясняют «почему». Сообщения коммитов — по-русски, по делу, с завершающей строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Команды ниже даны для Git Bash на Windows (`.venv/Scripts/python`); на Linux/macOS — `.venv/bin/python`.

## Review Focus

1. **Нет `.env` или в нём нет `KEITARO_API_KEY`/`KEITARO_BASE_URL`** — приложение должно падать при старте с ошибкой, называющей переменную, а Alembic — работать (ему нужен только `DATABASE_URL`). Тесты: Task 1 `test_settings_require_keitaro_variables`, Task 2 `test_database_settings_do_not_require_keitaro`.
2. **Ключ утекает через `repr`/логи настроек** — `repr(settings)` не содержит ключа. Тест: Task 1 `test_api_key_is_hidden_in_repr`.
3. **Путь к БД зависит от текущей папки** — SQLite по умолчанию лежит в `backend/adrobot.db` по абсолютному пути, где бы ни запускали. Тест: Task 1 `test_default_database_url_is_absolute_in_backend_dir`.
4. **Пробел в пути к файлу БД** (наш реальный путь) — движок и миграции работают. Тесты: Task 1 `test_engine_works_with_space_in_path`, Task 2 `test_migrations_upgrade_and_downgrade` (временная папка с пробелом).
5. **БД недоступна** — health-check отвечает 503 с `"database": "error"`, а не 500. Тест: Task 1 `test_health_reports_database_error`.

---

## Структура файлов

```
backend/
  pyproject.toml            — зависимости, настройки ruff и pytest
  alembic.ini               — без sqlalchemy.url (берётся из настроек)
  migrations/
    env.py                  — URL из DatabaseSettings или из config (для тестов); render_as_batch для SQLite
    script.py.mako
    versions/0001_baseline.py — пустая базовая ревизия
  app/
    __init__.py
    main.py                 — create_app()
    core/__init__.py
    core/config.py          — DatabaseSettings, Settings, get_settings(), пути
    db/__init__.py
    db/base.py              — Base (DeclarativeBase) с naming convention
    db/session.py           — create_db_engine(), create_session_factory()
    api/__init__.py
    api/health.py           — GET /api/health
  tests/
    conftest.py             — фикстура make_settings
    test_config.py
    test_db_session.py
    test_health.py
    test_migrations.py
frontend/                   — сгенерирован Angular CLI, правки ниже
.env.example                — дополняется
```

---

### Task 1: Бэкенд — проект, конфигурация, подключение к БД, health-check

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/db/__init__.py`, `backend/app/db/base.py`, `backend/app/db/session.py`, `backend/app/api/__init__.py`, `backend/app/api/health.py`
- Modify: `.env.example` (добавить переменные), `.env` (локально, не в git)
- Test: `backend/tests/conftest.py`, `backend/tests/test_config.py`, `backend/tests/test_db_session.py`, `backend/tests/test_health.py`

**Interfaces:**
- Produces (используют все следующие этапы):
  - `app.core.config`: константы `BACKEND_DIR: Path`, `REPOSITORY_ROOT: Path`, `ENV_FILE: Path` (= `REPOSITORY_ROOT / ".env"`), `DEFAULT_DATABASE_URL: str`; классы `DatabaseSettings(BaseSettings)` с полем `database_url: str` и `Settings(DatabaseSettings)`; `get_settings() -> Settings` (кэшируется `functools.lru_cache`).
  - Поля `Settings` (имя env-переменной = имя поля в верхнем регистре): `keitaro_base_url: str` (обязательное, без завершающего `/`), `keitaro_api_key: SecretStr` (обязательное), `keitaro_timeout_seconds: float = 10.0`, `keitaro_max_retries: int = 2`, `keitaro_write_name_prefix: str = ""`, `campaign_domain: str = ""`, `campaign_group: str = ""`, `campaign_traffic_source: str = ""`, `redirect_url: str = "https://google.com"`, `offers_cache_ttl_seconds: int = 300`, `cors_origins: list[str] = ["http://localhost:4200"]`.
  - `app.db.base.Base` — `DeclarativeBase` с `MetaData(naming_convention=…)`.
  - `app.db.session.create_db_engine(database_url: str) -> Engine`, `create_session_factory(engine: Engine) -> sessionmaker[Session]`.
  - `app.main.create_app(settings: Settings | None = None) -> FastAPI`; кладёт в `app.state`: `settings`, `engine`, `session_factory`.

- [ ] **Step 1: Создать `backend/pyproject.toml` и окружение**

Зависимости: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `pydantic>=2`, `pydantic-settings`, `httpx`. Dev-группа (`[project.optional-dependencies] dev`): `pytest`, `ruff`. `requires-python = ">=3.12"`. Настройки:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]
```

Run: `cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`
Expected: установка без ошибок.

- [ ] **Step 2: Написать падающие тесты конфигурации**

`backend/tests/conftest.py` — фикстура, создающая настройки без чтения реального `.env`:

```python
@pytest.fixture
def make_settings(tmp_path):
    def factory(**overrides) -> Settings:
        values = {
            "keitaro_base_url": "https://tracker.example.com/",
            "keitaro_api_key": "test-secret-key-123",
            "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)
    return factory
```

`backend/tests/test_config.py`:

```python
def test_settings_require_keitaro_variables(monkeypatch):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    message = str(error.value)
    assert "keitaro_base_url" in message
    assert "keitaro_api_key" in message

def test_api_key_is_hidden_in_repr(make_settings):
    settings = make_settings()
    assert "test-secret-key-123" not in repr(settings)
    assert "test-secret-key-123" not in str(settings.model_dump())
    assert settings.keitaro_api_key.get_secret_value() == "test-secret-key-123"

def test_base_url_trailing_slash_is_stripped(make_settings):
    assert make_settings().keitaro_base_url == "https://tracker.example.com"

def test_defaults(make_settings):
    settings = make_settings()
    assert settings.redirect_url == "https://google.com"
    assert settings.keitaro_write_name_prefix == ""
    assert settings.cors_origins == ["http://localhost:4200"]

def test_default_database_url_is_absolute_in_backend_dir():
    expected = (BACKEND_DIR / "adrobot.db").resolve().as_posix()
    assert DEFAULT_DATABASE_URL == f"sqlite:///{expected}"

def test_env_file_is_repository_root():
    assert ENV_FILE == REPOSITORY_ROOT / ".env"
    assert (REPOSITORY_ROOT / "CLAUDE.md").exists()
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.core.config'` или аналогично).

- [ ] **Step 4: Реализовать `backend/app/core/config.py`**

`BACKEND_DIR = Path(__file__).resolve().parents[2]`, `REPOSITORY_ROOT = BACKEND_DIR.parent`. `DatabaseSettings.model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")`. Завершающий `/` у `keitaro_base_url` срезается `field_validator`. `get_settings()` — `@lru_cache` над `Settings()`.

- [ ] **Step 5: Запустить — тесты конфигурации проходят**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 6: Написать падающие тесты подключения к БД и health-check**

`backend/tests/test_db_session.py`:

```python
def test_engine_works_with_space_in_path(tmp_path):
    folder = tmp_path / "folder with space"
    folder.mkdir()
    engine = create_db_engine(f"sqlite:///{(folder / 'app.db').as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1

def test_sqlite_foreign_keys_enabled(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

def test_session_factory_opens_sessions(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    with create_session_factory(engine)() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
```

`backend/tests/test_health.py`:

```python
def test_health_ok(make_settings):
    client = TestClient(create_app(make_settings()))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}

def test_health_reports_database_error(make_settings):
    app = create_app(make_settings())

    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("db is down"))

    app.state.engine = BrokenEngine()
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "error"}

def test_cors_allows_frontend_origin(make_settings):
    client = TestClient(create_app(make_settings()))
    response = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"
```

- [ ] **Step 7: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_db_session.py tests/test_health.py -v`
Expected: FAIL (модули `app.db.session`, `app.main` не найдены).

- [ ] **Step 8: Реализовать БД-слой, health-check и фабрику приложения**

- `app/db/base.py`: `Base(DeclarativeBase)` с `metadata = MetaData(naming_convention={"ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s", "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"})` — стабильные имена ограничений нужны Alembic для batch-миграций SQLite.
- `app/db/session.py`: для `sqlite` — `connect_args={"check_same_thread": False}` и обработчик события `connect`, выполняющий `PRAGMA foreign_keys=ON`; `create_session_factory` → `sessionmaker(bind=engine, expire_on_commit=False)`.
- `app/api/health.py`: `router = APIRouter(prefix="/api")`, `GET /health` берёт `request.app.state.engine`, выполняет `SELECT 1`; при `sqlalchemy.exc.SQLAlchemyError` — `JSONResponse(503, {"status": "error", "database": "error"})`.
- `app/main.py`: `create_app(settings=None)` — `settings or get_settings()`, движок и фабрика сессий в `app.state`, `CORSMiddleware(allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])`, подключение `health.router`. Глобального `app = create_app()` нет — запуск через `uvicorn --factory`.

- [ ] **Step 9: Запустить все тесты и линтер**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`
Expected: 12 passed; ruff без замечаний (при необходимости — `ruff format .` и повтор).

- [ ] **Step 10: Дополнить `.env.example` и локальный `.env`**

В `.env.example` добавить (значения-заглушки/по умолчанию):

```
KEITARO_TIMEOUT_SECONDS=10
KEITARO_MAX_RETRIES=2
# Writes to Keitaro are allowed only for campaigns whose name starts with this prefix (empty = no limit)
KEITARO_WRITE_NAME_PREFIX=
# Default: SQLite file in backend/. Example for Postgres: postgresql+psycopg://user:pass@localhost/adrobot
# DATABASE_URL=
CAMPAIGN_DOMAIN=
CAMPAIGN_GROUP=
CAMPAIGN_TRAFFIC_SOURCE=
REDIRECT_URL=https://google.com
OFFERS_CACHE_TTL_SECONDS=300
CORS_ORIGINS=["http://localhost:4200"]
```

`DATABASE_URL` закомментирован намеренно: пустой `DATABASE_URL=` перекрыл бы значение по умолчанию пустой строкой. В локальный `.env` добавить: `KEITARO_WRITE_NAME_PREFIX=test_oso4lq_`, `CAMPAIGN_DOMAIN=kylovoa.com`, `CAMPAIGN_GROUP=FORTESTS`, `CAMPAIGN_TRAFFIC_SOURCE=FORTESTS`.

- [ ] **Step 11: Проверить запуск с реальным `.env`**

Run: `cd backend && .venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000` (в фоне), затем `curl -s localhost:8000/api/health`
Expected: `{"status":"ok","database":"ok"}`; в выводе uvicorn нет значения ключа. Остановить сервер.

- [ ] **Step 12: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests .env.example
git commit -m "Каркас бэкенда: конфигурация, подключение к БД, health-check"
```

---

### Task 2: Alembic — базовая миграция, накат и откат

**Files:**
- Create: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_baseline.py`
- Test: `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `DatabaseSettings`, `BACKEND_DIR` (`app.core.config`), `Base` (`app.db.base`).
- Produces: цепочка ревизий с корнем `0001` (`down_revision = None`). Новые миграции этапов 2–3 ставят `down_revision` на последнюю ревизию; модели должны импортироваться в `migrations/env.py` (через `app.db.models`, когда появится), чтобы autogenerate их видел.

- [ ] **Step 1: Написать падающие тесты**

```python
def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config

def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    if not inspect(engine).has_table("alembic_version"):
        return None
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()

def test_migrations_upgrade_and_downgrade(tmp_path):
    folder = tmp_path / "db with space"
    folder.mkdir()
    url = f"sqlite:///{(folder / 'migrations.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    assert current_revision(url) == "0001"
    command.downgrade(alembic_config(url), "base")
    assert current_revision(url) is None
    command.upgrade(alembic_config(url), "head")
    assert current_revision(url) == "0001"

def test_database_settings_do_not_require_keitaro(monkeypatch):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = DatabaseSettings(_env_file=None)
    assert settings.database_url == DEFAULT_DATABASE_URL
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrations.py -v`
Expected: FAIL (нет `alembic.ini`).

- [ ] **Step 3: Настроить Alembic**

`alembic init migrations` из `backend/`, затем: в `alembic.ini` — `script_location = %(here)s/migrations`, строки `sqlalchemy.url` нет. В `migrations/env.py`: URL = `config.get_main_option("sqlalchemy.url")`, если задан (тесты), иначе `DatabaseSettings().database_url` (не `Settings` — миграциям не нужен ключ Keitaro); `target_metadata = Base.metadata`; `context.configure(..., render_as_batch=True)` в онлайн- и офлайн-режимах. Ревизия `versions/0001_baseline.py`: `revision = "0001"`, `down_revision = None`, пустые `upgrade()`/`downgrade()` — базовая точка, к которой цепляются таблицы этапов 2–3.

- [ ] **Step 4: Запустить тесты, ruff и CLI**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m alembic downgrade base && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m alembic current`
Expected: 14 passed; ruff чисто; последний вывод содержит `0001 (head)`; файл `backend/adrobot.db` создан (игнорируется git).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/migrations backend/tests/test_migrations.py
git commit -m "Alembic: базовая миграция, проверка наката и отката"
```

---

### Task 3: Фронтенд — пустой Angular-проект с прокси и линтером

**Files:**
- Create: `frontend/` (генерирует Angular CLI), `frontend/proxy.conf.json`
- Modify: `frontend/angular.json` (proxyConfig), `frontend/src/app/app.ts`, `frontend/src/app/app.html`, `frontend/src/app/app.spec.ts`, `frontend/eslint.config.js` (после `ng add angular-eslint`)

**Interfaces:**
- Produces: корневой компонент `App` (standalone) с `<router-outlet />` и пустыми маршрутами в `app.routes.ts` — страницы Create и Editor добавит этап 4; `pnpm start` проксирует `/api/*` на `http://localhost:8000`.

- [ ] **Step 1: Сгенерировать проект**

Run (из корня репозитория): `pnpm dlx @angular/cli@latest new frontend --package-manager pnpm --style css --routing --ssr false --skip-git --interactive false`
Expected: папка `frontend/` с установленными зависимостями. Если pnpm предупредил о заблокированных build-скриптах (esbuild и др.) — разрешить их через `pnpm approve-builds` в `frontend/` и повторить `pnpm install`. Если CLI не знает какой-то флаг — убрать его и выбрать то же значение интерактивно.

- [ ] **Step 2: Проверить строгость TypeScript**

Run: `grep -n '"strict"\|strictTemplates' frontend/tsconfig.json`
Expected: `"strict": true` и `"strictTemplates": true` (CLI ставит их по умолчанию; если нет — добавить).

- [ ] **Step 3: Заменить заглушку CLI на минимальную оболочку и обновить тест**

`app.html`: `<header><h1>Adrobot</h1></header>` + `<main><router-outlet /></main>`; из `app.ts` убрать неиспользуемые поля заглушки. Тест `app.spec.ts`:

```ts
it('renders the application title', async () => {
  const fixture = TestBed.createComponent(App);
  await fixture.whenStable();
  const heading = fixture.nativeElement.querySelector('h1') as HTMLHeadingElement;
  expect(heading.textContent).toContain('Adrobot');
});
```

Run: `cd frontend && pnpm ng test --watch=false`
Expected: тесты проходят.

- [ ] **Step 4: Прокси `/api` на бэкенд**

`frontend/proxy.conf.json`: `{ "/api": { "target": "http://localhost:8000", "secure": false } }`; в `angular.json` → `projects.frontend.architect.serve.options.proxyConfig = "proxy.conf.json"`.

- [ ] **Step 5: Линтер с правилом нового control flow**

Run: `cd frontend && pnpm ng add angular-eslint --skip-confirmation`
Затем в `eslint.config.js` для `*.html` добавить `"@angular-eslint/template/prefer-control-flow": "error"` (запрещает `*ngIf/*ngFor` — правило раздела 8 `CLAUDE.md`).
Run: `pnpm ng lint`
Expected: `All files pass linting.`

- [ ] **Step 6: Сборка**

Run: `cd frontend && pnpm ng build`
Expected: сборка без ошибок и предупреждений о бюджете.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "Пустой Angular-проект: прокси /api, angular-eslint, строгий TypeScript"
```

---

## Проверка готовности этапа

- [ ] Бэкенд: `cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` — всё зелёное.
- [ ] Миграции: `alembic downgrade base && alembic upgrade head` — без ошибок, `alembic current` → `0001 (head)`.
- [ ] Сквозная проверка: бэкенд на `:8000` (`uvicorn app.main:create_app --factory`), фронтенд `cd frontend && pnpm start`; `curl -s localhost:4200/api/health` → `{"status":"ok","database":"ok"}` (через прокси).
- [ ] `git status` чистый, в индексе нет `.env`, `*.db`, `node_modules`, `.venv`; `git push`.
- [ ] В итоговом сообщении этапа — что сделано и решения этапа (запуск через `--factory`, `DatabaseSettings` отдельно от `Settings`, пустая базовая ревизия `0001`).
