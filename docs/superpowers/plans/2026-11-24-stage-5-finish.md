# Этап 5 — финиш: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Проект готов к сдаче: уборка и проверка истории на секреты, Docker из двух контейнеров, ручной прогон сценария из видео на эмуляторе через Docker, `.env.example` и README.

**Architecture:** Код приложения не меняется. `backend` — образ Python, при старте применяет миграции и запускает uvicorn с фабрикой; `frontend` — сборка Angular, nginx отдаёт статику и проксирует `/api/` в `backend`. Ручной прогон идёт через этот стек против эмулятора Keitaro, браузер — Playwright MCP.

**Tech Stack:** Docker 29 / Compose v5, `python:3.14-slim`, `node:24-alpine` + pnpm (corepack), `nginx:alpine`, FastAPI, Alembic, Angular 22.

**Spec:** `docs/superpowers/specs/2026-11-24-stage-5-finish-design.md`

## Global Constraints

- Код в `backend/app/` и `frontend/src/` не меняется. Исключение — ошибка, найденная прогоном: исправление с тестом отдельным коммитом (superpowers:systematic-debugging).
- Секреты (ключ API, адрес трекера, в том числе эмулятора) — только в `.env`; в репозитории, образах, логах и документах их нет. В документах — «адрес из `KEITARO_BASE_URL`».
- `.env` не копируется в образы; контейнеру передаётся через `env_file`.
- Keitaro: создаются и меняются только объекты с префиксом `test_oso4lq_`; на эмуляторе `DELETE` безвозвратный, кампании прогона не удаляются.
- Образы: `python:3.14-slim`, `node:24-alpine`, `nginx:alpine`. Порт на хосте `8080:80`. В Docker `DATABASE_URL=sqlite:////data/adrobot.db`, `/data` — именованный том.
- Документация по-русски. Коммиты по-русски, в конце строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- История не переписывается, force-push запрещён.
- Ветки на GitHub удаляются только с разрешения владельца.

## Review Focus

1. **Нет `.env` или пустая обязательная переменная.** Compose должен остановиться с понятной ошибкой («env file … not found»), а бэкенд — упасть с именем переменной без её значения. Проверка — в задаче 2, шаги 6–7.
2. **Обновление страницы на глубокой ссылке** (`/editor/154`, `/create`). nginx отдаёт `index.html`, а не 404. Проверка — в задаче 2, шаг 5.
3. **Бэкенд остановлен.** nginx отвечает 502, интерфейс показывает «Бэкенд недоступен (HTTP 502)», как при dev-прокси. Проверка — в задаче 3, шаг 9.
4. **Перезапуск стека.** Миграции при повторном старте ничего не ломают, журнал созданных кампаний сохраняется в томе. Проверка — в задаче 2, шаг 8, и в задаче 3, шаг 10.
5. **Checkout на Windows с CRLF** (`core.autocrlf=true`). В образы не копируются shell-скрипты: команда старта записана в `CMD` через `sh -c`, nginx переносит CRLF в конфиге. Проверка — сборка из этого checkout в задаче 2.

---

### Task 1: Уборка и проверка истории на секреты

**Files:**
- Modify: `.gitignore`
- Modify: `docs/decisions.md` (новый раздел в конце)

**Interfaces:**
- Produces: раздел `## 2026-11-24 — этап 5 (финиш)` в `docs/decisions.md`; задачи 3 и 4 дописывают в него подразделы.

- [ ] **Step 1: Добавить в `.gitignore` блок «Local Claude Code and plugin state»: `.claude/`, `.superpowers/`.** Проверка: `git status --short` не показывает `.claude/`.
- [ ] **Step 2: Удалить локальный worktree и ветку этапа 3.** Сначала убедиться: `git -C .claude/worktrees/stage-3-editor-backend status --short` пусто, `git branch --merged main` содержит `worktree-stage-3-editor-backend`. Затем `git worktree remove .claude/worktrees/stage-3-editor-backend` и `git branch -d worktree-stage-3-editor-backend`. Локальную `stage-4-frontend` (влита) — тоже `git branch -d`. Ветки на GitHub не трогать.
- [ ] **Step 3: Проверка истории на секреты — скрипт в scratchpad, не в репозитории.** Для `.env` и `.env.backup-2026-11-24` взять значения `KEITARO_API_KEY`, `KEITARO_ADMIN_PASSWORD` (если не пусто) и хост из `KEITARO_BASE_URL` (без схемы и пути). Для каждого значения напечатать только имя переменной, файл и число вхождений `git log --all -p | grep -c -F -- "$value"`; само значение не печатать. Отдельно: `git log --all --name-only --format= | grep -E '(^|/)\.env$|\.(db|sqlite3?)$'` — ожидается пусто.
  Ожидается: все счётчики `0`, список файлов пуст. Если что-то найдено — остановиться и сообщить владельцу (имя переменной и коммит, без значения).
- [ ] **Step 4: Записать в `docs/decisions.md` раздел `## 2026-11-24 — этап 5 (финиш)` с подразделами «История не переписывается (владелец)» (почему: история читаемая и опубликована, force-push сломал бы ссылки PR #1 и #2) и «Проверка истории на секреты» (что и как проверено, итог, без значений).**
- [ ] **Step 5: Коммит.**
  ```bash
  git add .gitignore docs/decisions.md
  git commit -m "Уборка: локальные папки инструментов в .gitignore, проверка истории на секреты"
  ```

### Task 2: Docker — два контейнера в compose

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`
- Create: `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`
- Create: `docker-compose.yml`
- Modify: `docs/decisions.md` (подраздел «Docker»)

**Interfaces:**
- Produces: сервисы `backend` (внутренний порт 8000, не публикуется) и `frontend` (`http://localhost:8080`), том `adrobot-data`. Команды для задач 3–4: `docker compose up --build -d`, `docker compose stop backend`, `docker compose logs backend`, `docker compose down` (без `-v`: том остаётся).

- [ ] **Step 1: `backend/Dockerfile` и `backend/.dockerignore`.**
  - Образ `python:3.14-slim`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `WORKDIR /app`.
  - Скопировать `pyproject.toml`, `app/`, `migrations/`, `alembic.ini`; выполнить `pip install --no-cache-dir .`.
  - Создать непривилегированного пользователя и `/data`, принадлежащий ему.
  - `ENV DATABASE_URL=sqlite:////data/adrobot.db`, `EXPOSE 8000`.
  - `CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]`.
  - `.dockerignore`: `.venv`, `__pycache__`, `*.py[cod]`, `*.db`, `*.egg-info`, `.pytest_cache`, `.ruff_cache`, `tests`, `tools`, `.env*`.
- [ ] **Step 2: `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`.**
  - Шаг `build`: `node:24-alpine`, `corepack enable`, копирование `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, затем `pnpm install --frozen-lockfile`, затем остальные файлы и `pnpm build`.
  - Шаг запуска: `nginx:alpine`, `COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html`, `nginx.conf` в `/etc/nginx/conf.d/default.conf`.
  - `nginx.conf`: `listen 80`; `location /api/ { proxy_pass http://backend:8000; }` с заголовками `Host` и `X-Forwarded-For`, `proxy_read_timeout 90s` (с запасом над `KEITARO_TIMEOUT_SECONDS × (KEITARO_MAX_RETRIES + 1)` при значениях по умолчанию); `location / { try_files $uri $uri/ /index.html; }`.
  - `.dockerignore`: `node_modules`, `dist`, `.angular`, `.env*`.
- [ ] **Step 3: `docker-compose.yml` в корне.**
  - `backend`: `build: ./backend`, `env_file: .env`, `environment: DATABASE_URL: sqlite:////data/adrobot.db`, том `adrobot-data:/data`. Healthcheck через `python -c` с `urllib.request.urlopen("http://127.0.0.1:8000/api/health")`, интервал 5 с, 12 попыток.
  - `frontend`: `build: ./frontend`, `ports: ["8080:80"]`, `depends_on: backend: condition: service_healthy`.
  - `volumes: adrobot-data:`.
- [ ] **Step 4: Сборка и запуск.** `docker compose up --build -d`, затем `docker compose ps`. Ожидается: `backend` в состоянии `healthy`, `frontend` — `running`. `docker compose logs backend` показывает выполненные миграции до `0003` и старт uvicorn; ключа и адреса трекера в логах нет.
- [ ] **Step 5: Проверки через nginx.**
  - `curl -s localhost:8080/api/health` → `{"status":"ok","database":"ok"}`.
  - `curl -s localhost:8080/api/countries` → JSON-список, в нём есть `AU`.
  - `curl -s -o /dev/null -w '%{http_code}' localhost:8080/editor/154` → `200`, тело совпадает с `/` (переход на `index.html`).
  - `docker compose exec backend id -u` → не `0`.
  - `docker compose exec backend ls -a /app` → `.env` нет.
- [ ] **Step 6: Нет `.env`.** Во временной копии файла compose без `.env` (в scratchpad, не в репозитории) выполнить `docker compose config`. Ожидается ошибка, в которой упомянут отсутствующий `.env`.
- [ ] **Step 7: Пустая обязательная переменная.** `docker compose run --rm -e KEITARO_API_KEY= backend`. Ожидается: выход с ошибкой, в выводе есть `keitaro_api_key`, а значения ключа из `.env` нет (сверить `grep -c -F` без печати значения).
- [ ] **Step 8: Повторный старт.** `docker compose restart backend`. Ожидается: снова `healthy`, `alembic upgrade head` ничего не применяет, `/api/health` → ok.
- [ ] **Step 9: Подраздел «Docker» в `docs/decisions.md`.** Описать: два контейнера (владелец); миграции при старте; SQLite в томе; бэкенд наружу не публикуется, CORS не нужен; тесты и инструменты не попадают в образ; почему нет shell-скрипта (CRLF при checkout на Windows); таймаут прокси.
- [ ] **Step 10: Коммит.**
  ```bash
  git add backend/Dockerfile backend/.dockerignore frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore docker-compose.yml docs/decisions.md
  git commit -m "Docker: бэкенд с миграциями при старте и фронтенд на nginx в compose"
  ```

### Task 3: Ручной прогон сценария из видео на эмуляторе через Docker

**Files:**
- Modify: `docs/decisions.md` (подраздел «Ручной прогон через Docker»)
- Возможны исправления кода с тестами — только если прогон найдёт ошибку (отдельный коммит до записи результата).

**Interfaces:**
- Consumes: стек из задачи 2 (`http://localhost:8080`), `.env` с эмулятором и `KEITARO_WRITE_NAME_PREFIX=test_oso4lq_`; `cd backend && .venv/Scripts/python -m tools.stream_snapshot save|diff STREAM_ID PATH`.

После каждого шага экран сверяется с Keitaro: `GET /streams/{id}` через наш клиент или админка эмулятора. Цвет потока проверяется по вычисленному фону карточки: белый — `rgb(255, 255, 255)`, жёлтый — `rgb(255, 243, 176)`.

- [ ] **Step 1: Create.** `http://localhost:8080` → Create: Name `test_oso4lq_final_run`, Geo `AU`, Offer `18011`. Ожидается блок «Кампания создана» с id, alias, ссылкой и двумя потоками, строка журнала `created`. В Keitaro: Flow 1 — `redirect` на `https://google.com`, фильтр `country` accept `AU`, позиция 1; Flow 2 — 18011/100, позиция 2.
- [ ] **Step 2: Открыть в редакторе → Fetch Streams.** Flow 1 — «поток без офферов», Flow 2 — 18011 100%, оба потока белые.
- [ ] **Step 3: Снимок Flow 2 до первого Push** — в scratchpad: `python -m tools.stream_snapshot save <flow2> <scratchpad>/final-run-flow2.json`.
- [ ] **Step 4: Довести поток до трёх офферов, как в начале ролика.** Add 18012 → Push, затем Add 18013 → Push. Ожидается 34/33/33 и на экране, и в Keitaro.
- [ ] **Step 5: Шаги ролика.**
  - Add 18014: 25×4, поток жёлтый, 18014 «не опубликован», в Keitaro по-прежнему 34/33/33. Затем Push: поток белый, в Keitaro 25×4.
  - Add 18015 → Cancel: после Add 20×5, после Cancel 25×4, 18015 исчез, поток белый.
  - Remove 18014: 34/33/33, 18014 серый 0% в архиве с Bring back, поток жёлтый. Затем Push: поток белый, в Keitaro 18014 нет.
  - Bring back 18014: 25×4, поток жёлтый. Затем Push: поток белый, в Keitaro 25×4.
- [ ] **Step 6: Удаление в Keitaro.** В админке эмулятора (Playwright) удалить из Flow 2 офферы 18013 и 18014, затем Fetch Streams. Ожидается: 18013 и 18014 серые 0% с Bring back, остальные показаны с долями из Keitaro как есть. Эмулятор сам пересчитывает доли оставшихся, это записано в этапе 4.
- [ ] **Step 7: Pin 18011 → Bring back 18013 → Push.** У 18011 вес не меняется, есть пометка «закреплён», остальные делят остаток, «Итого: 100%». Поток жёлтый, после Push белый. В Keitaro те же доли.
- [ ] **Step 8: Fetch при черновике.** Add 18015 → Fetch Streams. Ожидается: черновик сохранён, видны сообщение и кнопка «Fetch Streams с отбросом черновиков». В подтверждении «Отмена» не отправляет запрос. «Отбросить и загрузить» делает поток белым, и он совпадает с Keitaro.
- [ ] **Step 9: Бэкенд остановлен.** `docker compose stop backend` → Fetch Streams. Ожидается «Бэкенд недоступен (HTTP 502)», состояние потока не изменилось. Затем `docker compose start backend`.
- [ ] **Step 10: Перезапуск и глубокая ссылка.** `docker compose down`, затем `docker compose up -d`, обновить страницу `/editor/<id>`. Ожидается: та же кампания в том же состоянии, на странице Create в журнале есть строка `test_oso4lq_final_run`.
- [ ] **Step 11: Итоговое сравнение со снимком.** `python -m tools.stream_snapshot diff <flow2> <scratchpad>/final-run-flow2.json` → «Расхождений нет».
- [ ] **Step 12: Миграции на чистой базе.** Из `backend/`: `DATABASE_URL=sqlite:///<scratchpad>/migrations-check.db`, затем `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`. Ожидается: все три команды без ошибок.
- [ ] **Step 13: Записать подраздел «Ручной прогон через Docker» в `docs/decisions.md`.** Таблица «Шаг | Экран | Keitaro | Итог» по образцу живой проверки этапа 3, плюс шаги 8–12. Кампания остаётся в эмуляторе. Расхождения записать с причиной.
- [ ] **Step 14: Коммит.**
  ```bash
  git add docs/decisions.md
  git commit -m "Ручной прогон сценария из видео на эмуляторе через Docker"
  ```

### Task 4: `.env.example` и README

**Files:**
- Modify: `.env.example`
- Create: `README.md`

**Interfaces:**
- Consumes: команды задач 2–3; разделы `docs/decisions.md`; `docs/keitaro-examples/README.md`; docstring-и `backend/tools/*.py`.

- [ ] **Step 1: `.env.example`.** Переменные остаются те же и в том же порядке. Добавить комментарии:
  - для эмулятора: `CAMPAIGN_DOMAIN=1813` (домен задаётся по id, его имя не совпадает с настоящим), `CAMPAIGN_GROUP=FORTESTS`, `CAMPAIGN_TRAFFIC_SOURCE=FORTESTS` — в виде закомментированного примера;
  - рекомендуется `KEITARO_WRITE_NAME_PREFIX=test_<ник>_`;
  - в Docker `DATABASE_URL` задаёт compose, `CORS_ORIGINS` не нужен;
  - на эмуляторе логин и пароль админки не нужны, вход через GitHub.
  Адрес эмулятора не писать.
  Проверка: `Settings` читает файл без ошибок типов, если подставить фиктивные ключ и адрес.
- [ ] **Step 2: `README.md` по разделам дизайна.**
  - Что это: две части.
  - Как устроено:
    - слои `api → services → keitaro client → repositories`;
    - локальное представление и черновики;
    - Push меняет только офферы;
    - клиент Keitaro скрыт за интерфейсом.
  - Требования: Docker, или Python ≥ 3.12, Node 24 и pnpm 11.
  - Таблица переменных `.env`.
  - Быстрый старт в Docker.
  - Локальный запуск:
    - venv, `pip install -e ".[dev]"`, `alembic upgrade head`, `uvicorn app.main:create_app --factory --reload`;
    - `pnpm install`, `pnpm start`;
    - активация venv для Windows и для Unix.
  - Миграции: накат, откат, новая ревизия.
  - Тесты и линтеры: `pytest`, `ruff check .`, `pnpm test`, `pnpm lint`, `pnpm build`.
  - Демо-стенд: `python -m tools.demo_stand` и маршруты `/demo`.
  - Вспомогательные команды: `python -m app.cli.recon`, `tools.compare_campaigns`, `tools.stream_snapshot`, `tools.archive_test_campaign` — с пометкой, что на эмуляторе удаление безвозвратное.
  - Решения кратко, со ссылками на разделы `docs/decisions.md`:
    - округление весов;
    - крайние случаи закрепления;
    - Fetch при черновике;
    - Cancel;
    - добавление в поток без офферов;
    - выбор кампании;
    - защита записи префиксом;
    - компенсация;
    - история не переписывается.
  - Как проверялось: тесты, эталон из админки (пример 25), живая проверка (пример 26), прогон через Docker.
  - Ограничения: эмулятор не равен Keitaro, трафик не проверялся, Postgres не входит в зависимости.
  - Ссылки на дизайн и планы.
- [ ] **Step 3: Выполнить каждую команду README.**
  - Бэкенд на свободном порту: `uvicorn … --port 8001`, `curl /api/health`.
  - Фронтенд: `pnpm install --frozen-lockfile`, `pnpm test`, `pnpm lint`, `pnpm build`.
  - `pytest`, `ruff check .`.
  - Демо-стенд на свободном порту, `curl /demo/keitaro/streams/2`.
  - Docker-команды уже проверены в задаче 2.
  Ожидается: всё проходит. Команда, которая не сработала, правится в README.
- [ ] **Step 4: Проверка на секреты в новых файлах.** Скриптом из задачи 1 (scratchpad) убедиться, что значений из `.env` нет ни в `README.md`, ни в `.env.example`, ни в `docker-compose.yml`, ни в `docs/decisions.md`. Ожидается: все счётчики `0`.
- [ ] **Step 5: Коммит.**
  ```bash
  git add .env.example README.md
  git commit -m "README и .env.example: запуск, Docker, миграции, тесты, решения"
  ```

### Task 5: Итоговая проверка и PR

**Files:**
- Изменений нет, если проверки зелёные.

- [ ] **Step 1: Полный прогон.**
  - `cd backend && .venv/Scripts/python -m pytest -q` и `.venv/Scripts/python -m ruff check .`;
  - `cd frontend && pnpm test && pnpm lint && pnpm build`;
  - `docker compose build`.
  Ожидается: всё зелёное, тестов не меньше, чем было: 353 бэкенд, 80 фронтенд.
- [ ] **Step 2: `git status --short` пусто; `git ls-files` не содержит `.env`, `*.db`, `.claude/`, `.playwright-mcp/`, `*.webp`.**
- [ ] **Step 3: Итоговое ревью всей ветки** (superpowers:requesting-code-review), исправления отдельными коммитами.
- [ ] **Step 4: Push ветки `stage-5-finish` и PR в `main`.** В описании PR: что сделано, как проверено, ссылки на дизайн и план. В конце строка `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Вливает владелец.
- [ ] **Step 5: Спросить владельца об удалении веток на GitHub** (`stage-4-frontend`, `worktree-stage-3-editor-backend`). Удалять только после его ответа.
