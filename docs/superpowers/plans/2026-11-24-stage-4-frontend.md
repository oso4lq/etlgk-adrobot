# Этап 4 — фронтенд на Angular и демо-стенд. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Страницы Create и Editor на Angular поверх готовой API и демо-стенд с Keitaro в памяти. Готово, когда на демо-стенде в браузере проходится весь ролик из видео, все кнопки работают и итог потока там, где веса считает обёртка, — 100%.

**Architecture:** Тонкие API-сервисы на `HttpClient` → хранилища страниц со состоянием в signals → чистые функции-мапперы «ответ API + состояние UI → view-model» → `computed` → компоненты только отображают (подход A дизайна). Демо-стенд — модуль `backend/tools/demo_stand.py`: `create_app` с `FakeKeitaroClient`, заполненным как в видео, и демо-маршрутами `/demo/...`.

**Tech Stack:** Angular 22.2 (standalone, signals, zoneless, Signal Forms `@angular/forms/signals`), TypeScript strict, RxJS 7.8, vitest через `ng test`, angular-eslint, pnpm; бэкенд — Python, FastAPI, pytest, ruff, uvicorn.

**Spec:** `docs/superpowers/specs/2026-11-24-stage-4-frontend-design.md` (дизайн этапа, согласован владельцем 2026-11-24); общий дизайн `docs/superpowers/specs/2026-11-18-adrobot-design.md`, раздел 7; `docs/decisions.md` (тексты и коды ошибок API, правила весов, Fetch и Push); правила — `CLAUDE.md`, разделы 1, 8, 9.

## Global Constraints

- API бэкенда не меняется. Если фронтенду чего-то не хватает — остановиться и согласовать с владельцем. В `backend/` меняются только `tools/demo_stand.py` и `tests/test_demo_stand.py`.
- Веса, статусы, `is_draft`, `can_push`, `can_cancel`, проблемы и предупреждения берутся только из ответа API. Фронтенд их не пересчитывает и не угадывает. Итог «Итого: N%» — сумма `weight` активных офферов из ответа.
- Шаблоны: только `@if`, `@for`, `@switch`. Отображаются только поля готового view-model: никаких вызовов методов, геттеров, пайпов и вычислений в шаблоне. Разрешены чтение signal (`view()`) и обработчики событий `(click)="store.action(...)"`.
- TypeScript: `for...of` вместо цепочек `.filter().map()`; методы `Object` (keys, values, entries) — только когда нужно обойти всё подряд. Имена без сокращений, комментарии объясняют «почему».
- Названия элементов управления — по-английски, ровно так: `Name`, `Geo`, `Offer`, `Create`, `Fetch Streams`, `Push to KT`, `Cancel`, `Remove`, `Bring back`, `Pin`, `Unpin`, `Add`. Остальной текст — по-русски. Сообщения ошибок API показываются как есть.
- Без UI-библиотек и новых зависимостей фронтенда. Стили минимальные: белый фон чистого потока, жёлтый — черновика, серые строки архива.
- Хранилища (`CreatorStore`, `EditorStore`) предоставляются в `providers` компонента страницы, API-сервисы — `providedIn: 'root'`. Только хранилища вызывают API-сервисы.
- Демо-стенд не читает `.env` и не обращается к настоящему Keitaro; его код не попадает в `backend/app/`, фронтенд не знает о `/demo`.
- Ветка `stage-4-frontend`, в `main` — через PR, который сливает владелец. Первый коммит ветки — дизайн этапа и этот план. Коммиты по-русски, по делу, последняя строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Команды — Git Bash на Windows, путь с пробелом — в кавычках. Фронтенд — из `frontend/`: `pnpm ng test --watch=false`, `pnpm ng lint`, `pnpm ng build` (Node ≥ 24.15; сейчас активен 26.13.1 — подходит). Бэкенд — из `backend/`: `.venv/Scripts/python -m pytest -q`, `.venv/Scripts/python -m ruff check .`. Если работа идёт в отдельном worktree — сначала `pnpm install` в `frontend/` и своя `.venv` в `backend/` (`python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`).
- Реальный Keitaro на этом этапе не трогается (Admin API отвечает 403). Если доступ вернётся — живая проверка этапа 3 по его плану (Task 12), отдельно от этого плана.

## Review Focus

1. **Бэкенд не запущен, а dev-сервер Angular работает.** Прокси отвечает 502/504 без JSON. Пользователь видит «Бэкенд недоступен (HTTP 504)», а не пустой экран или исключение. Тест: Task 2 `maps proxy error without JSON body to backend_unavailable`.
2. **Двойное нажатие или нажатие во время другого запроса по тому же потоку или во время Fetch.** Второй запрос не уходит. Тесты: Task 7 `ignores a second action on a busy stream`, `ignores stream actions while fetching`; Task 4 `ignores a second submit while creating`.
3. **Пользователь переключил кампанию, пока шёл запрос по предыдущей.** Поздний ответ по старой кампании не затирает новую: ни ответ открытия, ни ответ Fetch, ни ответ действия с потоком. Тест: Task 7 `drops late responses for a previously opened campaign`.
4. **Ответы автокомплита пришли не по порядку** (медленный ответ на «1» после быстрого на «12»). Показываются подсказки только для последнего ввода. Тест: Task 3 `shows suggestions only for the latest query`.
5. **В адресе мусор: `/editor/abc`, `/editor/0`, `/editor/1.5`.** Запрос не уходит, страница показывает «Некорректный id кампании». Тест: Task 6 `parseCampaignId rejects non-positive and non-integer ids`; Task 7 `open with invalid id shows error without request`.

---

## Файлы

```
backend/tools/demo_stand.py                 демо-стенд: данные, настройки, база, /demo-маршруты, запуск
backend/tests/test_demo_stand.py

frontend/src/app/
  app.ts, app.html, app.css, app.spec.ts     шапка со ссылками Create / Editor (изменить)
  app.config.ts                              provideHttpClient(withFetch()), provideRouter(routes, withComponentInputBinding())
  app.routes.ts                              '' → /create, create, editor, editor/:campaignId
  core/api-types.ts                          типы ответов API (поля как в JSON, snake_case)
  core/api-error.ts (+ .spec.ts)             ApiError и toApiError
  core/format.ts (+ .spec.ts)                formatDateTime, toOfferOption — общие для обеих страниц
  shared/autocomplete/autocomplete.ts, .html, .css (+ .spec.ts)
  creator/creator-api.ts                     CreatorApi
  creator/creator-view.ts (+ .spec.ts)       toCreatorView
  creator/creator-store.ts (+ .spec.ts)      CreatorStore
  creator/create-page.ts, .html, .css (+ .spec.ts)
  editor/editor-api.ts                       EditorApi
  editor/editor-view.ts (+ .spec.ts)         toEditorView, parseCampaignId
  editor/editor-store.ts (+ .spec.ts)        EditorStore
  editor/editor-page.ts, .html, .css (+ .spec.ts)
  editor/stream-card.ts, .html, .css (+ .spec.ts)

docs/decisions.md                            раздел «этап 4» (Task 9)
```

---

### Task 1: Демо-стенд

**Files:**
- Create: `backend/tools/demo_stand.py`
- Test: `backend/tests/test_demo_stand.py`

**Interfaces:**
- Consumes: `create_app(settings, keitaro_client)` (`app/main.py`); `Settings` (`app/core/config.py`, конструктор `Settings(_env_file=None, ...)`); `FakeKeitaroClient` и его помощники `add_offer`, `add_campaign`, `add_stream`, `set_stream_offers` (`tests/fakes.py`); Alembic — как `alembic_config` в `tests/test_migrations.py` (`Config(BACKEND_DIR / "alembic.ini")`, `config.attributes["database_url"] = url`, `command.upgrade(config, "head")`).
- Produces:
  - `DEMO_CAMPAIGN_NAME = "test_oso4lq_demo_video"`, `FOREIGN_CAMPAIGN_NAME = "partner_campaign_demo"`, `DEMO_DATABASE_PATH = BACKEND_DIR / "demo_stand.db"` (под `*.db` в `.gitignore`).
  - `build_demo_keitaro() -> FakeKeitaroClient`.
  - `demo_settings(database_url: str) -> Settings`.
  - `prepare_database(path: Path) -> str` — удаляет файл, если есть, мигрирует до `head`, возвращает URL `sqlite:///...`.
  - `demo_router(keitaro: FakeKeitaroClient) -> APIRouter` — префикс `/demo`.
  - `build_demo_app(database_url: str) -> FastAPI` — `create_app(demo_settings(url), keitaro_client=build_demo_keitaro())` плюс `demo_router`. Фейк доступен как `app.state.keitaro_client`.
  - `main(argv: list[str] | None = None) -> int` — `--host` (по умолчанию `127.0.0.1`), `--port` (по умолчанию `8000`), печатает, что это демо-стенд без настоящего Keitaro, и адреса `/api`, `/docs`, `/demo/keitaro/streams/{id}`, затем `uvicorn.run`.

Начальные данные `build_demo_keitaro()` (в этом порядке, поэтому id фейка: кампании 1 и 2, потоки 1, 2, 3):
- каталог офферов (поверх 18813 фейка): 501 «Demo offer A», 502 «Demo offer B», 503 «Demo offer C», 504 «Demo offer D», 505 «Demo offer E», 506 «Demo offer F»;
- кампания `DEMO_CAMPAIGN_NAME`: поток «Australia → Google» (позиция 1, без офферов), поток «Offers» (позиция 2, офферы `[(501, 34), (502, 33), (503, 33)]`);
- кампания `FOREIGN_CAMPAIGN_NAME`: поток «Partner offers» (позиция 1, `[(504, 100)]`).

`demo_settings`: `keitaro_base_url="https://keitaro.demo.invalid"`, `keitaro_api_key="demo-stand-not-a-real-key"`, `keitaro_write_name_prefix="test_oso4lq_"`, `campaign_domain="kylovoa.com"`, `campaign_group="FORTESTS"`, `campaign_traffic_source="FORTESTS"`, `database_url=<аргумент>`.

Демо-маршруты:
- `GET /demo/keitaro/streams/{stream_id}` → `{"id", "campaign_id", "name", "type", "position", "state", "schema", "action_type", "offers": [{"offer_id", "share", "state"}], "total_share"}`; `total_share` — сумма `share` офферов в состоянии `active`.
- `POST /demo/keitaro/streams/{stream_id}/offers/{offer_id}/delete` → убирает оффер из потока фейка через `set_stream_offers` (остальные строки — с прежними `share` и `state`, доли не пересчитываются), отвечает тем же телом, что GET.
- Неизвестный поток или оффер не в потоке → `404 {"code": "demo_not_found", "message": "..."}`.

- [ ] **Step 0: Создать ветку и закоммитить дизайн и план**

Run (из корня): `git switch -c stage-4-frontend && git add docs/superpowers/specs/2026-11-24-stage-4-frontend-design.md docs/superpowers/plans/2026-11-24-stage-4-frontend.md && git commit -m "Этап 4: дизайн фронтенда и демо-стенда, план"`

- [ ] **Step 1: Написать падающие тесты** (`TestClient` поверх `build_demo_app(prepare_database(tmp_path / "demo.db"))`)

- `test_demo_keitaro_matches_video` — кампания `test_oso4lq_demo_video` с двумя потоками: позиция 1 без офферов, позиция 2 с `[(501, 34), (502, 33), (503, 33)]`; офферы 501–506 в `list_offers()`; есть кампания `partner_campaign_demo`.
- `test_demo_settings_ignore_env_file(monkeypatch)` — с `KEITARO_BASE_URL` и `KEITARO_API_KEY` в окружении `demo_settings(...)` всё равно даёт `https://keitaro.demo.invalid` и `demo-stand-not-a-real-key`.
- `test_prepare_database_recreates_file` — файл с мусором → после `prepare_database` в нём таблица `alembic_version` с ревизией `head`; повторный вызов не падает.
- `test_demo_stream_route_shows_keitaro_state` — GET по потоку «Offers»: три оффера, `total_share == 100`, `schema == "landings"`.
- `test_demo_delete_route_removes_offer_without_rebalancing` — delete 502 → в ответе 501 (34) и 503 (33), `total_share == 67`; затем `POST /api/editor/campaigns/{id}/fetch` → оффер 502 со статусом `removed`.
- `test_demo_routes_answer_404_for_unknown_objects` — неизвестный поток и оффер не в потоке → 404, `code == "demo_not_found"`.
- `test_demo_stand_runs_add_and_push` — fetch → `POST /api/editor/streams/{id}/offers {"offer_id": 504}` → веса `[25, 25, 25, 25]` → push 200 → демо-GET показывает четыре оффера по 25.
- `test_demo_stand_refuses_push_to_foreign_campaign` — fetch чужой кампании → Remove 504 → в ответе `can_push is False`, в `problems` есть `write_forbidden`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_demo_stand.py -q`
Expected: FAIL — `ModuleNotFoundError: tools.demo_stand`.

- [ ] **Step 3: Реализовать `backend/tools/demo_stand.py`** по Interfaces. В docstring модуля — назначение и команда запуска (`python -m tools.demo_stand [--port 8000]`), по образцу `tools/archive_test_campaign.py`.

- [ ] **Step 4: Убедиться, что тесты проходят, весь набор и ruff зелёные**

Run: `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check .`
Expected: все тесты PASS, `All checks passed!`.

- [ ] **Step 5: Ручной запуск**

Run: `cd backend && .venv/Scripts/python -m tools.demo_stand --port 8765` (в фоне), затем `curl -s localhost:8765/api/keitaro-campaigns` и `curl -s localhost:8765/demo/keitaro/streams/2`; остановить процесс.
Expected: в списке обе демо-кампании; поток 2 — три оффера, `total_share` 100.

- [ ] **Step 6: Коммит** — `git add backend/tools/demo_stand.py backend/tests/test_demo_stand.py && git commit -m "Демо-стенд: бэкенд с Keitaro в памяти, заполненным как в видео"`

---

### Task 2: Каркас фронтенда — типы API, ошибки, маршруты, шапка

**Files:**
- Create: `frontend/src/app/core/api-types.ts`, `frontend/src/app/core/api-error.ts`, `frontend/src/app/core/api-error.spec.ts`
- Modify: `frontend/src/app/app.config.ts`, `app.routes.ts`, `app.ts`, `app.html`, `app.css`, `app.spec.ts`, `frontend/src/styles.css`

**Interfaces:**
- Produces (`core/api-types.ts`) — поля один в один с JSON нашей API (`backend/app/schemas/`):
  - `ApiNotice {code: string; message: string}`;
  - `OfferBinding {offer_id: number; name: string; status: 'active' | 'removed'; weight: number; is_pinned: boolean; is_published: boolean}`;
  - `EditorStream {keitaro_stream_id: number; name: string; position: number; has_offers: boolean; is_draft: boolean; can_push: boolean; can_cancel: boolean; offers: OfferBinding[]; problems: ApiNotice[]; warnings: ApiNotice[]}`;
  - `EditorCampaign {keitaro_campaign_id: number; name: string; write_allowed: boolean; last_fetched_at: string; streams: EditorStream[]}`;
  - `FetchResult {campaign: EditorCampaign; kept_draft_stream_ids: number[]; notices: ApiNotice[]}`;
  - `KeitaroCampaignSummary {id: number; name: string}`, `OfferSummary {id: number; name: string}`, `Country {code: string; name: string}`;
  - `CreatedCampaign` и `JournalEntry` — поля `CreatedCampaignResponse` и `JournalEntryResponse` из `backend/app/schemas/creator.py` (даты — `string`, nullable — `| null`).
- Produces (`core/api-error.ts`): `interface ApiError {code: string; message: string; status: number}` и `toApiError(error: unknown): ApiError`.
- Produces: маршруты `''` → `redirectTo: 'create'`, `create` → `CreatePage` (lazy `loadComponent`), `editor` и `editor/:campaignId` → `EditorPage` (lazy). Пока страниц нет — временные заглушки в тех же файлах, что создадут Task 5 и Task 8 (`creator/create-page.ts`, `editor/editor-page.ts`) с классами `CreatePage` и `EditorPage`.

- [ ] **Step 1: Написать падающие тесты `api-error.spec.ts`**

- `keeps code and message from an API error body` — `new HttpErrorResponse({status: 409, error: {code: 'stream_not_draft', message: 'Нечего публиковать…'}})` → `{code: 'stream_not_draft', message: 'Нечего публиковать…', status: 409}`.
- `maps status 0 to backend unavailable` → `{code: 'network_error', message: 'Бэкенд недоступен', status: 0}`.
- `maps proxy error without JSON body to backend_unavailable` — статусы 502, 503, 504 с телом-строкой → `{code: 'backend_unavailable', message: 'Бэкенд недоступен (HTTP 504)', status: 504}`.
- `maps other bodies to unexpected_response` — 500 с телом `'oops'` → `message: 'Неожиданный ответ сервера (HTTP 500)'`; тело `{code: 1}` (не строки) — так же.
- `maps non-HTTP errors to unexpected_error` — `new Error('x')` → `{code: 'unexpected_error', message: 'Непредвиденная ошибка', status: 0}`.

- [ ] **Step 2: Обновить `app.spec.ts`** — `renders navigation links` — в шапке ссылки с текстом `Create` и `Editor` и `href` `/create` и `/editor` (нужен `provideRouter([])`).

- [ ] **Step 3: Убедиться, что тесты падают** — `cd frontend && pnpm ng test --watch=false`. Expected: FAIL (нет `api-error`, нет ссылок).

- [ ] **Step 4: Реализовать** типы, `toApiError`, `app.config.ts` (`provideHttpClient(withFetch())`, `provideRouter(routes, withComponentInputBinding())`), маршруты, шапку (`routerLink`, `routerLinkActive`), базовые стили в `styles.css` (шрифт, отступы, классы `.stream--clean` белый, `.stream--draft` жёлтый, `.offer--archived` серый, `.total--off` выделение).

- [ ] **Step 5: Проверить** — `pnpm ng test --watch=false && pnpm ng lint && pnpm ng build`. Expected: тесты PASS, `All files pass linting.`, сборка без ошибок.

- [ ] **Step 6: Коммит** — `git commit -m "Фронтенд: типы API, разбор ошибок, маршруты Create и Editor"`

---

### Task 3: Автокомплит

**Files:**
- Create: `frontend/src/app/shared/autocomplete/autocomplete.ts`, `autocomplete.html`, `autocomplete.css`, `autocomplete.spec.ts`

**Interfaces:**
- Consumes: `toApiError` (Task 2).
- Produces:
  - `interface AutocompleteOption {id: number; label: string}`;
  - `type AutocompleteSearch = (query: string) => Observable<AutocompleteOption[]>`;
  - компонент `Autocomplete`, селектор `app-autocomplete`. Входы: `label = input.required<string>()` (видимая подпись поля, связана с `<input>` через `id`), `search = input.required<AutocompleteSearch>()`, `selection = input<AutocompleteOption | null>(null)`, `hiddenIds = input<ReadonlySet<number>>(new Set())`, `disabled = input(false)`. Выход: `selectionChange = output<AutocompleteOption | null>()`.
- Поведение: ввод и фокус → через 250 мс `search(текст)`; новый ввод отменяет прежний запрос (`switchMap`). Подсказки без `hiddenIds`. Клик по подсказке → `selectionChange.emit(option)`, текст поля = `option.label`, список закрыт. Правка текста после выбора → один раз `selectionChange.emit(null)`. Вход `selection` стал `null` снаружи → поле очищается. Ошибка поиска → строка «Поиск недоступен: {message}». Компонент управляемый: выбранное значение хранит родитель (хранилище).

- [ ] **Step 1: Написать падающие тесты** (`vi.useFakeTimers()`, функция поиска — `Subject` на каждый запрос, тестовый хост-компонент)

- `searches after a 250 ms pause` — ввод «50» → до 250 мс вызовов нет, после — один вызов с «50».
- `shows suggestions only for the latest query` — ввод «1», пауза, ввод «12», пауза; ответ на «12» приходит раньше ответа на «1» → показаны только подсказки для «12».
- `hides options listed in hiddenIds`.
- `emits the chosen option and closes the list`.
- `emits null once when the text is edited after a choice`.
- `clears the text when selection becomes null`.
- `shows a search error message` — поиск отвечает ошибкой `{code, message: 'Keitaro недоступен'}` → текст «Поиск недоступен: Keitaro недоступен».

- [ ] **Step 2: Убедиться, что тесты падают** — `pnpm ng test --watch=false`. Expected: FAIL (нет компонента).
- [ ] **Step 3: Реализовать `Autocomplete`.** Подсказки для шаблона готовит `computed` компонента (уже без скрытых id). Клавиатура (стрелки, Enter, Escape) — по возможности.
- [ ] **Step 4: Проверить** — `pnpm ng test --watch=false && pnpm ng lint`. Expected: PASS.
- [ ] **Step 5: Коммит** — `git commit -m "Автокомплит: поиск с задержкой, отмена устаревших запросов, управляемый выбор"`

---

### Task 4: Создаватор — API, маппер, хранилище

**Files:**
- Create: `frontend/src/app/core/format.ts`, `format.spec.ts`, `frontend/src/app/creator/creator-api.ts`, `creator-view.ts`, `creator-view.spec.ts`, `creator-store.ts`, `creator-store.spec.ts`

**Interfaces:**
- Consumes: типы и `toApiError` (Task 2), `AutocompleteOption`, `AutocompleteSearch` (Task 3).
- Produces:
  - `CreatorApi` (`providedIn: 'root'`): `countries(): Observable<Country[]>` (`GET /api/countries`), `searchOffers(query: string): Observable<OfferSummary[]>` (`GET /api/offers?query=`), `createCampaign(body: {name: string; country: string; offer_id: number}): Observable<CreatedCampaign>` (`POST /api/campaigns`), `journal(): Observable<JournalEntry[]>` (`GET /api/created-campaigns`).
  - `core/format.ts`: `toOfferOption(offer: OfferSummary): AutocompleteOption` — подпись `"18813 — Test offer"`; `formatDateTime(iso: string): string` — `dd.MM.yyyy, HH:mm`, локальное время, `Intl.DateTimeFormat('ru-RU', …)`. Обе нужны и Create, и Editor (Task 6, 7), поэтому лежат в `core`. Тесты `format.spec.ts`: подпись оффера; `formatDateTime('2026-11-24T10:05:00+00:00')` совпадает с тем же моментом, отформатированным `Intl.DateTimeFormat('ru-RU', …)` (не зависит от часового пояса машины).
  - `toCreatorView(input: CreatorViewInput): CreatorView`, где `CreatorViewInput = {countries: Country[]; offer: AutocompleteOption | null; nameValid: boolean; countryValid: boolean; submitting: boolean; result: CreatedCampaign | null; error: string | null; journal: JournalEntry[]; journalError: string | null}`, а `CreatorView = {countryOptions: {code: string; label: string}[]; createDisabled: boolean; error: string | null; result: CreatedCampaignView | null; journalRows: JournalRowView[]; journalError: string | null}`.
  - `CreatedCampaignView = {title: string; lines: {label: string; value: string}[]; campaignUrl: string; editorLink: string}`; `editorLink` = `/editor/{keitaro_campaign_id}`.
  - `JournalRowView = {createdAt: string; name: string; country: string; offerId: string; status: string; keitaroCampaignId: string; error: string; needsCleanup: boolean}`; пустые значения — `"—"`; `needsCleanup` — статус `compensation_failed`; дата — `formatDateTime`.
  - `CreatorStore` (`@Injectable()`, без `providedIn`): `model = signal({name: '', country: ''})`; `createForm = form(this.model, path => { required(path.name); maxLength(path.name, 255); required(path.country); })`; `offer = signal<AutocompleteOption | null>(null)`; `searchOffers: AutocompleteSearch`; `view = computed(...)`; действия `load(): void` (страны и журнал), `selectOffer(option: AutocompleteOption | null): void`, `submit(): void`.
- Правила: `nameValid` — форма валидна по имени и `name.trim() !== ''`; `createDisabled` — `!nameValid || !countryValid || offer === null || submitting`. `submit()` при `createDisabled` ничего не делает. Успех: `result` заполнен, `error` сброшен, форма и `offer` очищены, журнал перезагружен. Ошибка: `error = message`, форма и `offer` сохранены, журнал перезагружен (сбой записан и в журнал бэкенда). В запрос уходит `name.trim()`.

- [ ] **Step 1: Написать падающие тесты маппера** (`creator-view.spec.ts`, без TestBed)
  - `labels countries as code and name` — `{code: 'AU', name: 'Australia'}` → `'AU — Australia'`, порядок сохранён.
  - `disables Create until name, country and offer are set` и `while submitting`.
  - `describes the created campaign with an editor link` — `editorLink == '/editor/215338'`, в `lines` есть alias, страна, оффер, id обоих потоков.
  - `marks compensation_failed journal rows for cleanup and fills empty cells with a dash`.
- [ ] **Step 2: Написать падающие тесты хранилища** (`creator-store.spec.ts`, `provideHttpClient()`, `provideHttpClientTesting()`, `HttpTestingController`)
  - `loads countries and journal`.
  - `posts trimmed name and clears the form on success` — тело `{name: 'test_oso4lq_x', country: 'AU', offer_id: 18813}`; после ответа `result` есть, `model().name === ''`, `offer() === null`, ушёл повторный `GET /api/created-campaigns`.
  - `keeps the input and shows the API message on failure` — 422 `{code: 'name_prefix_required', message: '…'}` → `view().error` — этот текст, имя и оффер на месте.
  - `ignores a second submit while creating` — два `submit()` подряд → один `POST`.
- [ ] **Step 3: Убедиться, что тесты падают** — `pnpm ng test --watch=false`. Expected: FAIL.
- [ ] **Step 4: Реализовать** `core/format.ts`, `CreatorApi`, `creator-view.ts`, `CreatorStore`. Поле `Geo` в Task 5 привязывается к `createForm.country` тем же `[formField]`.
- [ ] **Step 5: Проверить** — `pnpm ng test --watch=false && pnpm ng lint`. Expected: PASS.
- [ ] **Step 6: Коммит** — `git commit -m "Создаватор на фронтенде: API, view-model, хранилище формы"`

---

### Task 5: Страница Create

**Files:**
- Create/replace: `frontend/src/app/creator/create-page.ts`, `create-page.html`, `create-page.css`, `create-page.spec.ts`

**Interfaces:**
- Consumes: `CreatorStore` (Task 4), `Autocomplete` (Task 3), `FormField` (`[formField]`) из `@angular/forms/signals`.
- Produces: компонент `CreatePage` (`providers: [CreatorStore]`), вызывает `store.load()` при создании.

Разметка по дизайну 5.3: поле `Name` (`[formField]="store.createForm.name"`), `<select>` `Geo` с пустым первым вариантом «Выберите страну» и `view().countryOptions`, `<app-autocomplete label="Offer">`, кнопка `Create` (`[disabled]="view().createDisabled"`), ошибка, блок «Кампания создана» (`lines`, ссылка `campaignUrl`, `routerLink` «Открыть в редакторе»), таблица журнала «Созданные кампании» (строка с `needsCleanup` выделена).

- [ ] **Step 1: Написать падающие тесты** (`HttpTestingController`)
  - `renders Name, Geo, Offer and a disabled Create button`.
  - `shows the result block with an editor link after creation` — после ответа `POST` в DOM текст «Кампания создана» и ссылка с `href="/editor/215338"`.
- [ ] **Step 2: Убедиться, что тесты падают.** Expected: FAIL.
- [ ] **Step 3: Реализовать `CreatePage`.**
- [ ] **Step 4: Проверить** — `pnpm ng test --watch=false && pnpm ng lint && pnpm ng build`. Expected: PASS.
- [ ] **Step 5: Коммит** — `git commit -m "Страница Create: форма, результат со ссылкой в редактор, журнал"`

---

### Task 6: View-model редактора — чистые функции

**Files:**
- Create: `frontend/src/app/editor/editor-view.ts`, `frontend/src/app/editor/editor-view.spec.ts`

**Interfaces:**
- Consumes: типы (Task 2), `AutocompleteOption` (Task 3), `formatDateTime` (`core/format.ts`, Task 4).
- Состояние страницы описывают два поля: `loadStatus` — чем кончилось открытие кампании; `pageError` — текст последней неудачной операции уровня страницы (открытие или Fetch).
- Produces:
  - `type LoadStatus = 'idle' | 'loading' | 'not-fetched' | 'ready' | 'error'`.
  - `parseCampaignId(raw: string | undefined): number | null` — только целое > 0 из цифр.
  - `interface EditorViewInput {campaignId: number | null; campaign: EditorCampaign | null; loadStatus: LoadStatus; pageError: string | null; fetching: boolean; fetchNotices: ApiNotice[]; keptDraftStreamIds: number[]; forceFetchConfirmOpen: boolean; busyStreamIds: ReadonlySet<number>; streamErrors: ReadonlyMap<number, string>; offerSelections: ReadonlyMap<number, AutocompleteOption>}`.
  - `toEditorView(input: EditorViewInput): EditorView`:
    - `EditorView = {header: CampaignHeaderView | null; statusMessage: string | null; errorMessage: string | null; showFetchButton: boolean; fetchDisabled: boolean; notices: string[]; forceFetch: ForceFetchView; streams: StreamView[]}`;
    - `CampaignHeaderView = {title: string; details: string; writeForbiddenNote: string | null}`;
    - `ForceFetchView = {offered: boolean; confirmOpen: boolean; confirmText: string; disabled: boolean}`;
    - `StreamView = {id: number; title: string; idLabel: string; cssClass: string; isDraft: boolean; hasOffers: boolean; activeOffers: OfferRowView[]; archivedOffers: OfferRowView[]; showArchive: boolean; showTotal: boolean; totalLabel: string; totalIsOff: boolean; problems: string[]; warnings: string[]; error: string | null; pushDisabled: boolean; cancelDisabled: boolean; addDisabled: boolean; hiddenOfferIds: ReadonlySet<number>; offerSelection: AutocompleteOption | null}`;
    - `OfferRowView = {offerId: number; label: string; weightLabel: string; isPinned: boolean; isUnpublished: boolean; actionsDisabled: boolean}`.

Тексты (точно):
- `statusMessage`: `loading` → «Загрузка…»; `not-fetched` → «Кампания {id} ещё не загружена в редактор»; `idle` → «Выберите кампанию»; `ready` и `error` → `null`. `errorMessage` — `pageError` как есть (при любом статусе).
- `header.details`: «Keitaro id {id} · Fetch: {formatDateTime(last_fetched_at)}». `writeForbiddenNote` при `write_allowed = false`: «Публикация в эту кампанию запрещена (защита по префиксу)».
- `notices`: тексты `fetchNotices`; если `keptDraftStreamIds` не пуст — ещё «Черновики сохранены в потоках: {имена через запятую}» (имена по id из кампании).
- `forceFetch.confirmText`: «Неопубликованные изменения в потоках {имена} будут потеряны».
- `idLabel`: «id {keitaro_stream_id}». `label` оффера: «{offer_id} — {name}». `weightLabel`: «{weight}%». `totalLabel`: «Итого: {сумма}%».

Правила:
- `showFetchButton` — `campaignId !== null` и статус не `loading` (Fetch — выход и из `not-fetched`, и из ошибки открытия); `fetchDisabled` — `fetching` или есть занятые потоки.
- `forceFetch.offered` — `keptDraftStreamIds` не пуст; `disabled` — как `fetchDisabled`.
- `cssClass`: `stream stream--plain` (без офферов), `stream stream--draft` (`is_draft`), иначе `stream stream--clean`.
- Активные — `status === 'active'`, архив — `removed`, порядок как в ответе. `showArchive` — архив не пуст. `showTotal` — есть активные; `totalIsOff` — сумма ≠ 100.
- `busy` потока = id в `busyStreamIds` или `fetching`. `pushDisabled = !can_push || busy`; `cancelDisabled = !can_cancel || busy`; `addDisabled = busy || нет выбора`; `actionsDisabled = busy`.
- `hiddenOfferIds` — id активных офферов потока. `problems`/`warnings` — `message` как есть. `error` — из `streamErrors`.

- [ ] **Step 1: Написать падающие тесты** (таблица случаев, без TestBed)
  - `parseCampaignId rejects non-positive and non-integer ids` — `'abc'`, `'0'`, `'-1'`, `'1.5'`, `''`, `undefined` → `null`; `'215338'` → `215338`.
  - `shows a plain stream without offers or buttons`.
  - `colors a draft stream yellow and a clean stream white`.
  - `splits active offers and archive, labels weights and the total` — `[(501, 25, active), (502, 25, active, pinned), (503, 0, removed)]` → активные «25%», «25%», `isPinned` у 502, архив «0%», `totalLabel` «Итого: 50%», `totalIsOff`.
  - `marks unpublished offers`.
  - `disables push and cancel from the API flags and while busy or fetching`.
  - `disables Add until an offer is chosen and hides active offers from suggestions`.
  - `passes problems, warnings and the stream error through`.
  - `describes not-fetched, loading, error and idle states` — в том числе `error` без кампании: `errorMessage` задан, `showFetchButton` истинно.
  - `offers a forced fetch naming the streams with kept drafts`.
  - `notes when writing to the campaign is forbidden`.
- [ ] **Step 2: Убедиться, что тесты падают.** Expected: FAIL.
- [ ] **Step 3: Реализовать `editor-view.ts`.**
- [ ] **Step 4: Проверить** — `pnpm ng test --watch=false && pnpm ng lint`. Expected: PASS.
- [ ] **Step 5: Коммит** — `git commit -m "Редактор: view-model потоков и офферов — чистые функции"`

---

### Task 7: Редактор — API и хранилище

**Files:**
- Create: `frontend/src/app/editor/editor-api.ts`, `editor-store.ts`, `editor-store.spec.ts`

**Interfaces:**
- Consumes: типы и `toApiError` (Task 2), `AutocompleteOption`/`AutocompleteSearch` (Task 3), `toOfferOption` (`core/format.ts`, Task 4), `toEditorView`, `parseCampaignId`, `LoadStatus` (Task 6).
- Produces:
  - `EditorApi` (`providedIn: 'root'`): `searchCampaigns(query)` (`GET /api/keitaro-campaigns?query=`), `searchOffers(query)` (`GET /api/offers?query=`), `getCampaign(id)` (`GET /api/editor/campaigns/{id}`), `fetch(id, force: boolean)` (`POST /api/editor/campaigns/{id}/fetch`, `?force=true` только при `force`), `addOffer(streamId, offerId)` (`POST /api/editor/streams/{id}/offers`, тело `{offer_id}`), `removeOffer`, `bringBackOffer`, `pinOffer`, `unpinOffer` (`POST .../offers/{offerId}/remove|bring-back|pin|unpin`), `push(streamId)`, `cancel(streamId)` (`POST .../push|cancel`). Действия с потоком возвращают `Observable<EditorStream>`.
  - `EditorStore` (`@Injectable()`): сигналы из `EditorViewInput` (Task 6) и `view = computed(() => toEditorView(...))`; `searchCampaigns: AutocompleteSearch` (подпись «{id} — {name}»), `searchOffers: AutocompleteSearch` (`toOfferOption`); действия `open(rawId: string | undefined): void`, `fetch(): void`, `requestForceFetch(): void`, `confirmForceFetch(): void`, `dismissForceFetch(): void`, `selectOffer(streamId: number, option: AutocompleteOption | null): void`, `addOffer(streamId)`, `removeOffer(streamId, offerId)`, `bringBackOffer(streamId, offerId)`, `pinOffer(streamId, offerId)`, `unpinOffer(streamId, offerId)`, `push(streamId)`, `cancel(streamId)`.

Правила:
- `open`: всё состояние сбрасывается. `parseCampaignId` → `null` → `campaignId = null`, статус `error`, `pageError` «Некорректный id кампании», запроса нет. Иначе `loading`, `getCampaign`: 200 → `ready`; 404 с `code === 'campaign_not_fetched'` → `not-fetched`; прочее → `error`, `pageError = message`.
- Каждый ответ (открытие, Fetch, действие) применяется, только если `campaignId` с момента запроса не сменился.
- `fetch`/`confirmForceFetch`: при `fetching` или занятых потоках — ничего. Успех: `campaign`, `ready`, `pageError = null`, `fetchNotices`, `keptDraftStreamIds`, ошибки потоков сброшены, подтверждение закрыто. Ошибка: `pageError = message`, `loadStatus` и загруженная кампания не меняются.
- Действие с потоком: при `fetching` или занятом потоке — ничего. Поток занят до ответа. Успех: поток в `campaign` заменяется ответом по `keitaro_stream_id`, ошибка потока сброшена; после `addOffer` выбор оффера потока очищается. Ошибка: `streamErrors[streamId] = message`, кампания не меняется. В любом случае поток освобождается.

- [ ] **Step 1: Написать падающие тесты** (`HttpTestingController`)
  - `open with invalid id shows error without request`.
  - `opens a fetched campaign` / `reports a campaign that was not fetched yet` (404 `campaign_not_fetched`) / `shows other open errors`.
  - `fetch stores notices and offers a forced fetch for kept drafts` → `confirmForceFetch()` → запрос с `force=true`, после ответа предложения нет.
  - `fetch failure keeps the loaded campaign and shows the message` — `view().errorMessage` — текст ответа, потоки на месте.
  - `replaces only the changed stream with the action response`.
  - `clears the offer selection after a successful add`.
  - `records an action error on the stream and frees it` — 409 `keitaro_stream_changed` → `view().streams[1].error` — текст ответа, `pushDisabled` снова по `can_push`.
  - `ignores a second action on a busy stream` — `push(2)` дважды → один запрос.
  - `ignores stream actions while fetching`.
  - `drops late responses for a previously opened campaign` — `open('1')`, `open('2')`; ответ для 2, затем для 1 → на экране кампания 2. То же для ответа действия, начатого до смены кампании.
- [ ] **Step 2: Убедиться, что тесты падают.** Expected: FAIL.
- [ ] **Step 3: Реализовать `EditorApi` и `EditorStore`.**
- [ ] **Step 4: Проверить** — `pnpm ng test --watch=false && pnpm ng lint`. Expected: PASS.
- [ ] **Step 5: Коммит** — `git commit -m "Редактор: API и хранилище — Fetch, действия с потоком, защита от повторных нажатий"`

---

### Task 8: Страница Editor и карточка потока

**Files:**
- Create: `frontend/src/app/editor/stream-card.ts`, `.html`, `.css`, `.spec.ts`
- Create/replace: `frontend/src/app/editor/editor-page.ts`, `.html`, `.css`, `.spec.ts`

**Interfaces:**
- Consumes: `EditorStore` (Task 7), `StreamView`, `OfferRowView` (Task 6), `Autocomplete` (Task 3).
- Produces:
  - `StreamCard`, селектор `app-stream-card`: вход `stream = input.required<StreamView>()`, `searchOffers = input.required<AutocompleteSearch>()`; выходы `offerSelected = output<AutocompleteOption | null>()`, `add`, `push`, `cancel` (`output<void>()`), `remove`, `bringBack`, `pin`, `unpin` (`output<number>()` — id оффера). Карточка ничего не вызывает сама: `EditorPage` переводит выходы в действия хранилища с id потока.
  - `EditorPage` (`providers: [EditorStore]`): вход маршрута `campaignId = input<string>()`; `effect` вызывает `store.open(campaignId())`, когда параметр задан. Выбор в автокомплите кампаний → `router.navigate(['/editor', option.id])`.

Разметка по дизайну 5.4: выбор кампании (`<app-autocomplete label="Кампания">`), `statusMessage`, `errorMessage`, шапка кампании, кнопка `Fetch Streams`, `notices`, кнопка «Fetch Streams с отбросом черновиков» и блок подтверждения («Отбросить и загрузить» / «Отмена»), список `<app-stream-card>`. Карточка: заголовок, пометка «черновик», для простого потока — «поток без офферов»; таблица активных (вес, «закреплён», «не опубликован», `Remove`, `Pin`/`Unpin`), строка итога, «Архив» с `Bring back`, проблемы, предупреждения, ошибка, автокомплит `Offer` + `Add`, `Push to KT`, `Cancel`.

- [ ] **Step 1: Написать падающие тесты**
  - `stream-card.spec.ts`: `renders a draft stream with the draft class and enabled push`; `renders archived offers with Bring back and 0%`; `renders a plain stream without buttons`; `emits remove with the offer id`.
  - `editor-page.spec.ts` (`HttpTestingController`, `provideRouter`): `shows Fetch Streams for a campaign that was not fetched` — маршрут `campaignId='7'`, 404 `campaign_not_fetched` → текст «Кампания 7 ещё не загружена в редактор» и кнопка `Fetch Streams`; `asks for confirmation before a forced fetch`.
- [ ] **Step 2: Убедиться, что тесты падают.** Expected: FAIL.
- [ ] **Step 3: Реализовать `StreamCard` и `EditorPage`.**
- [ ] **Step 4: Проверить** — `pnpm ng test --watch=false && pnpm ng lint && pnpm ng build`. Expected: PASS, сборка без ошибок и предупреждений о бюджете.
- [ ] **Step 5: Коммит** — `git commit -m "Страница Editor: выбор кампании, Fetch Streams, карточки потоков"`

---

### Task 9: Приёмка на демо-стенде, журнал решений, PR

**Files:**
- Modify: `docs/decisions.md` (новый раздел «2026-11-24 — этап 4 (фронтенд)»)

- [ ] **Step 1: Запустить стенд и фронтенд** — `cd backend && .venv/Scripts/python -m tools.demo_stand` (порт 8000, в фоне) и `cd frontend && pnpm start` (в фоне).
- [ ] **Step 2: Пройти ролик через Playwright MCP** — шаги 1–8 раздела 9 дизайна. На каждом шаге сверить экран с `GET http://localhost:8000/demo/keitaro/streams/{id}`; на шаге 7 удалить офферы `POST /demo/keitaro/streams/{id}/offers/{offer_id}/delete`. Ожидаемые числа: шаг 1 — 34/33/33; шаг 2 — 25×4; шаг 5 после Remove — 34/33/33 и 0%; шаг 7 — две строки по 25%, «Итого: 50%», проблема «…веса пересчитаются…»; шаг 8 — 25 (закреплён) и 38/37, «Итого: 100%».
- [ ] **Step 3: Дополнительные проверки** из раздела 9 дизайна: Fetch при черновике → подтверждение → отброс; чужая кампания — `Push to KT` неактивна, видна проблема `write_forbidden`; Create (`test_oso4lq_demo_create`, AU, оффер 501) → блок результата, строка журнала, «Открыть в редакторе» → `Fetch Streams` показывает два потока; бэкенд остановлен → на экране «Бэкенд недоступен…».
- [ ] **Step 4: Найденные расхождения** — исправить в задаче, которой принадлежит код (тест + исправление + коммит), и повторить шаг.
- [ ] **Step 5: Записать раздел «этап 4» в `docs/decisions.md`** — пункты из раздела 10 дизайна, разбор ошибок прокси (`backend_unavailable`, Task 2), отбрасывание поздних ответов при смене кампании (Task 7) и результат приёмки (что проверено, на чём, какие числа увидены). Остановить стенд и фронтенд.
- [ ] **Step 6: Финальная проверка** — `cd frontend && pnpm ng test --watch=false && pnpm ng lint && pnpm ng build`; `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check .`. Expected: всё зелёное.
- [ ] **Step 7: Коммит, push ветки и PR** — `git commit -m "Журнал решений этапа 4 и приёмка на демо-стенде"`, `git push -u origin stage-4-frontend`, `gh pr create --base main` (описание: что сделано, как запустить стенд, результат приёмки; в конце — строка `🤖 Generated with [Claude Code](https://claude.com/claude-code)`). PR сливает владелец.
