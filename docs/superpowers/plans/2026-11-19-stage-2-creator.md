# Этап 2 — создаватор кампаний. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бэкенд создаватора: `POST /api/campaigns` создаёт в Keitaro кампанию с двумя потоками (страна → `https://google.com`, остальные → оффер), с проверками до записи, компенсацией при сбое и журналом в БД; поиск офферов, список стран, журнал созданных кампаний. Готово, когда кампания, созданная через нашу API, совпадает поле за полем с эталоном `test_oso4lq_reference` (кампания 215193), собранным руками в админке.

**Architecture:** Слои по дизайну (6.1): роутеры `app/api/` → сервисы `app/services/` (создаватор, каталог офферов, справочники из конфигурации) → чистые функции `app/domain/` (страны, alias) → клиент `app/keitaro/` и репозиторий `app/repositories/`. Сервисы тестируются с in-memory фейком Keitaro (`tests/fakes.py`) и временной SQLite. Тела запросов к Keitaro — ровно те, что проверены реальным запросом (пример 24). Приёмка — команда `tools/compare_campaigns.py`, которая только читает Keitaro.

**Tech Stack:** Python ≥3.12 (локально 3.14), FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx, pycountry, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-18-adrobot-design.md` — разделы 4 (создаватор), 5.6 (защита по префиксу), 6.1–6.4, 8 (п. 5–7), 9 («Этап 2»); `docs/decisions.md` — разделы «этап 1» (В1–В7) и «этап 2: эталон из админки»; правила — `CLAUDE.md`, разделы 1, 5, 7, 8, 9.

## Global Constraints

- Не выдумывать API Keitaro: пути и поля — только из `docs/keitaro-openapi.json` или реальных ответов (`docs/keitaro-examples/`). Тела создания — пример 24 (поля админки по умолчанию) + 12/13 (фильтр страны, оффер).
- Запись в реальный Keitaro — только в Task 8 и только объекты с именем на `test_oso4lq_`: `test_oso4lq_creator_check` (создаётся через нашу API) и эталон `test_oso4lq_reference` (215193, архивируется после сравнения). `clean_archive` не вызывать никогда.
- Секреты — ключ API **и адрес трекера**: их нет в логах, ответах нашей API, сообщениях об ошибках, `docs/keitaro-examples/` и коммитах. В примерах адрес → `tracker.example.com`, ключ и `token` кампании → `***`.
- Логгеры `httpx`/`httpcore` остаются на WARNING (их поднимает `app.keitaro.http_session` при импорте); код этапа не настраивает логирование так, чтобы это снять.
- Повторы — как в этапе 1: запросы на создание автоматически не повторяются; повтор `POST /campaigns` допустим только с **новым** alias после ответа «alias занят».
- Защита общего Keitaro: если задан `KEITARO_WRITE_NAME_PREFIX`, создаватор принимает только имена с этим префиксом. Компенсация трогает только кампанию, созданную в этом же запросе (или найденную по нашему alias), и её потоки.
- Ответ об ошибке нашей API — `{"code": str, "message": str}` и осмысленный HTTP-статус, никогда не «голый» 500.
- Синхронный стек: обычные эндпоинты FastAPI, синхронные SQLAlchemy и `httpx.Client`.
- Схема БД меняется только миграциями Alembic; накат и откат работают.
- Комментарии объясняют «почему». Коммиты — по-русски, по делу, последняя строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Работа идёт в `main`, как на этапах 0–1; push — после подтверждения владельца.
- Команды — Git Bash на Windows, из `backend/`: `.venv/Scripts/python ...`; путь репозитория содержит пробел, его берём в кавычки.

## Review Focus

1. **Имя с пробелами по краям** (`"  test_oso4lq_x  "`): обрезается до проверки префикса, в Keitaro и журнал уходит обрезанным. Тест: Task 4 `test_name_is_trimmed_before_prefix_check`.
2. **Страна строчными буквами** (`"de"`): принимается, в фильтр потока уходит `"DE"`. Тест: Task 4 `test_country_code_is_normalized`.
3. **Keitaro недоступен во время проверки оффера:** ответ 502 `keitaro_unavailable`, ни одной записи в Keitaro и ни одной строки журнала. Тест: Task 4 `test_keitaro_down_during_validation_writes_nothing`.
4. **Keitaro не вернул `domain` в ответе на создание кампании:** ссылка кампании строится по имени домена из конфигурации, а не превращается в `None…alias`. Тест: Task 4 `test_campaign_url_falls_back_to_configured_domain`.
5. **Пустой, пробельный или нечисловой запрос автокомплита офферов:** не ошибка; пустой — первые офферы списка, нечисловой — поиск по названию. Тест: Task 3 `test_search_blank_query_returns_first_offers`, `test_search_text_query_matches_name_case_insensitively`.

---

## Структура файлов

```
backend/
  pyproject.toml                         — + pycountry
  app/core/errors.py                     — AppError: базовая ошибка с code/http_status/message
  app/keitaro/errors.py                  — KeitaroError наследует AppError
  app/keitaro/client.py                  — тела с полями админки; list_campaigns пропускает неразбираемые
  app/db/models.py                       — ORM CreatedCampaign, CreationStatus
  app/repositories/__init__.py
  app/repositories/created_campaigns.py  — CreatedCampaignsRepository (журнал)
  app/domain/__init__.py
  app/domain/countries.py                — Country, list_countries(), find_country()
  app/domain/alias.py                    — generate_alias()
  app/services/__init__.py
  app/services/offer_catalog.py          — OfferCatalog: кэш офферов с TTL, поиск, find()
  app/services/creator_references.py     — CreatorReferences, CreatorReferenceResolver, CreatorMisconfiguredError
  app/services/campaign_creator.py       — CampaignCreator: проверки, создание, компенсация; ошибки создаватора
  app/schemas/__init__.py
  app/schemas/creator.py                 — схемы нашей API для создаватора и журнала
  app/schemas/catalog.py                 — OfferResponse, CountryResponse
  app/api/dependencies.py                — сессия БД и сервисы из app.state
  app/api/creator.py                     — POST /api/campaigns, GET /api/created-campaigns
  app/api/catalog.py                     — GET /api/offers, GET /api/countries
  app/api/errors.py                      — обработчик AppError
  app/main.py                            — create_app(settings, keitaro_client), lifespan
  migrations/env.py                      — импорт app.db.models
  migrations/versions/0002_created_campaigns.py
  tools/compare_campaigns.py             — приёмка: сравнение двух кампаний поле за полем (только чтение)
  tools/archive_test_campaign.py         — уборка тестовой кампании с префиксом (потоки, затем кампания)
  tests/fakes.py                         — FakeKeitaroClient
  tests/conftest.py                      — + db_session
  tests/test_keitaro_client.py, test_migrations.py, test_created_campaigns_repository.py,
  tests/test_countries.py, test_offer_catalog.py, test_alias.py, test_creator_references.py,
  tests/test_campaign_creator.py, test_campaign_compensation.py, test_api_creator.py,
  tests/test_api_catalog.py, test_api_errors.py, test_compare_campaigns.py, test_archive_test_campaign.py
docs/keitaro-examples/25-creator-vs-reference.json, README.md
docs/decisions.md                        — раздел «этап 2»
```

---

### Task 1: Клиент Keitaro — тела с полями админки и устойчивый список кампаний

**Files:**
- Modify: `backend/app/keitaro/client.py` (`_campaign_body`, `_country_redirect_stream_body`, `_offers_stream_body`, `list_campaigns`)
- Modify: `docs/decisions.md`
- Test: `backend/tests/test_keitaro_client.py`

**Interfaces:**
- Consumes: `docs/keitaro-examples/24-create-campaign-admin-defaults.json` — `request.body` (кампания), `response` (ответ на создание), `observations.stream_bodies[0|1]` (тела Flow 1 и Flow 2), `observations.streams_after[0|1]` (потоки, прочитанные после создания).
- Produces: публичные сигнатуры `KeitaroClient` не меняются. Тела:
  - кампания — прежние поля + `"cost_auto": True, "uniqueness_method": "ip_ua", "uniqueness_param": "", "notes": ""`;
  - оба потока — прежние поля + `"weight": 100, "comments": ""`.
  - `list_campaigns()` возвращает только разобранные элементы; тело не-список → `KeitaroUnavailableError("Keitaro недоступен: некорректный ответ")`.

- [ ] **Step 1: Переписать тесты тел на пример 24**

`test_create_campaign_sends_verified_body`, `test_create_country_redirect_stream_sends_verified_body`, `test_create_offers_stream_sends_verified_body` берут ожидаемое тело из примера 24 (кампания — `request.body`, потоки — `observations.stream_bodies[i]`, ответ для replay — `response` и `observations.streams_after[i]` со статусом 200). Проверка та же: `json.loads(sent[0].content) == body`. Тест alias-конфликта (пример 11) не меняется.

Новые тесты:

```python
def test_list_campaigns_skips_unparseable_items(caplog):
    good = {"id": 1, "name": "a", "alias": "x1", "type": "position", "state": "active"}
    bad = {"id": 2, "name": None, "alias": "x2", "type": "position", "state": "active"}
    client = client_answering(200, [good, bad, {**good, "id": 3}], [])
    assert [campaign.id for campaign in client.list_campaigns()] == [1, 3]
    assert "skipped 1" in caplog.text and "x2" not in caplog.text

def test_list_campaigns_non_list_body_is_unavailable():
    with pytest.raises(KeitaroUnavailableError, match=UNAVAILABLE_MESSAGE):
        client_answering(200, {"error": "x"}, []).list_campaigns()
```

- [ ] **Step 2: Запустить — падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_client.py -q`
Expected: FAIL (тела без новых полей; `list_campaigns` падает на элементе с `name: None`).

- [ ] **Step 3: Реализовать**

Добавить поля в три функции тел; комментарий над ними сослаться на пример 24 и раздел «этап 2» в `docs/decisions.md`. `list_campaigns`: получить сырой ответ, если не `list` — `KeitaroUnavailableError` с тем же текстом, что у `_parse`; каждый элемент валидировать `TypeAdapter(KeitaroCampaign)`, неразобранные пропускать; один `logger.warning("Keitaro campaign list: skipped %d unparseable item(s)", count)` — без значений элементов (там чужие данные). Почему пропуск, а не отказ: инстанс общий, одна чужая кривая кампания не должна ломать поиск по alias при компенсации и выбор кампании в редакторе.

- [ ] **Step 4: Запустить — проходят**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: PASS (все тесты).

- [ ] **Step 5: Запись в `docs/decisions.md`** (раздел «этап 2») — «Список кампаний пропускает неразбираемые элементы»: что и почему (перенесено с этапа 3, нужно компенсации уже сейчас).

- [ ] **Step 6: Commit**

```bash
git add backend/app/keitaro/client.py backend/tests/test_keitaro_client.py docs/decisions.md
git commit -m "Клиент Keitaro: тела создания с полями админки, список кампаний без падения на чужих записях"
```

---

### Task 2: Журнал созданных кампаний — таблица, миграция, репозиторий

**Files:**
- Create: `backend/app/db/models.py`, `backend/migrations/versions/0002_created_campaigns.py`, `backend/app/repositories/__init__.py`, `backend/app/repositories/created_campaigns.py`
- Modify: `backend/migrations/env.py` (импорт `app.db.models`, чтобы метаданные были полными), `backend/tests/conftest.py` (фикстура `db_session`)
- Test: `backend/tests/test_migrations.py`, `backend/tests/test_created_campaigns_repository.py`

**Interfaces:**
- Produces:
  - `app.db.models.CreationStatus(StrEnum)`: `PENDING="pending"`, `CREATED="created"`, `FAILED="failed"`, `COMPENSATION_FAILED="compensation_failed"`.
  - `app.db.models.CreatedCampaign(Base)`, таблица `created_campaigns`: `id` int PK; `name` String(255) not null; `alias` String(32) null; `country` String(2) not null; `offer_id` int not null; `status` String(32) not null; `keitaro_campaign_id` int null; `country_stream_id` int null; `offers_stream_id` int null; `campaign_url` String(1024) null; `error` Text null; `created_at`, `updated_at` — `DateTime(timezone=True)` not null. (Два столбца потоков вместо `keitaro_stream_ids` из дизайна — потоков ровно два и у каждого своя роль; в decisions — Task 8.)
  - `app.repositories.created_campaigns.CreatedCampaignsRepository(session: Session)`:
    - `add_pending(name: str, country: str, offer_id: int) -> CreatedCampaign` — статус `pending`, время UTC, сразу `commit` (след остаётся, даже если процесс упадёт дальше);
    - `save(entry: CreatedCampaign) -> None` — обновляет `updated_at`, `commit`;
    - `list_recent(limit: int = 100) -> list[CreatedCampaign]` — новые первыми (по `id` убыванию).
  - фикстура `db_session` (conftest): временная SQLite в `tmp_path`, `create_db_engine` + `Base.metadata.create_all`, отдаёт `Session`, закрывает после теста.

- [ ] **Step 1: Тесты миграций** — в `test_migrations.py` ожидаемая голова `"0002"` вместо `"0001"`; новые:

```python
def test_created_campaigns_table_follows_migrations(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    columns = {c["name"] for c in inspect(create_engine(url)).get_columns("created_campaigns")}
    assert {"name", "alias", "country", "offer_id", "status", "keitaro_campaign_id",
            "country_stream_id", "offers_stream_id", "campaign_url", "error",
            "created_at", "updated_at"} <= columns
    command.downgrade(alembic_config(url), "0001")
    assert not inspect(create_engine(url)).has_table("created_campaigns")

def test_migrations_match_models(tmp_path):
    # A model change without a migration (or the reverse) must fail here, not in production.
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    with create_engine(url).connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
```
(Движки в тестах закрывать `dispose()`, как в `current_revision`.)

- [ ] **Step 2: Тесты репозитория** — `test_created_campaigns_repository.py`:

```python
def test_add_pending_is_committed_with_timestamps(db_session):
    entry = CreatedCampaignsRepository(db_session).add_pending("test_oso4lq_a", "DE", 18813)
    assert entry.id is not None and entry.status == CreationStatus.PENDING
    assert entry.created_at.tzinfo is not None

def test_save_updates_fields_and_timestamp(db_session): ...
    # status=CREATED, keitaro_campaign_id=5 → после save перечитанная строка их содержит,
    # updated_at >= created_at

def test_list_recent_returns_newest_first(db_session): ...
    # три add_pending → имена в обратном порядке
```

- [ ] **Step 3: Запустить — падают** (`ImportError`, голова `0001`).

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_migrations.py tests/test_created_campaigns_repository.py -q`

- [ ] **Step 4: Реализовать** модель, миграцию `0002` (`down_revision = "0001"`, `op.create_table`/`op.drop_table`, имена ограничений — по `NAMING_CONVENTION`), импорт моделей в `env.py`, репозиторий, фикстуру.

- [ ] **Step 5: Запустить все тесты — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest -q`

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/models.py backend/app/repositories backend/migrations backend/tests/conftest.py backend/tests/test_migrations.py backend/tests/test_created_campaigns_repository.py
git commit -m "Журнал созданных кампаний: таблица, миграция 0002, репозиторий"
```

---

### Task 3: Справочники формы — страны, каталог офферов, фейк Keitaro

**Files:**
- Modify: `backend/pyproject.toml` (`"pycountry>=24.6"` в `dependencies`), затем `cd backend && .venv/Scripts/python -m pip install -e ".[dev]"`
- Create: `backend/app/domain/__init__.py`, `backend/app/domain/countries.py`, `backend/app/services/__init__.py`, `backend/app/services/offer_catalog.py`, `backend/tests/fakes.py`
- Test: `backend/tests/test_countries.py`, `backend/tests/test_offer_catalog.py`

**Interfaces:**
- Produces:
  - `app.domain.countries.Country(code: str, name: str)` — frozen dataclass; `list_countries() -> list[Country]` — все страны ISO 3166-1 alpha-2 из pycountry, сортировка по `name`, результат кэшируется; `find_country(code: str) -> Country | None` — без учёта регистра и пробелов по краям.
  - `app.services.offer_catalog.OfferCatalog(client: KeitaroClient, ttl_seconds: float, clock: Callable[[], float] = time.monotonic)`:
    - `search(query: str, limit: int = 20) -> list[KeitaroOffer]`: запрос обрезается; пустой → первые `limit` офферов в порядке Keitaro; иначе оффер подходит, если `str(id)` начинается с запроса **или** запрос (casefold) входит в название (casefold); точное совпадение id — первым, остальные в порядке Keitaro.
    - `find(offer_id: int) -> KeitaroOffer | None`: из кэша; при промахе — одно принудительное обновление списка (оффер могли только что создать), затем `None`.
    - Список берётся `client.list_offers()` не чаще раза в `ttl_seconds` (`OFFERS_CACHE_TTL_SECONDS`); доступ к кэшу под `threading.Lock` (эндпоинты FastAPI идут в пуле потоков). Ошибки Keitaro пробрасываются как есть.
  - `tests/fakes.py: FakeKeitaroClient` — реализует весь `KeitaroClient` в памяти; используется Task 3–7 (и этапом 3):
    - конструктор без аргументов заполняет справочники как на тестовом инстансе: оффер `KeitaroOffer(id=18813, name="Test offer 18813", state="active")`, домен `(1813, "kylovoa.com")`, группа `(10332, "FORTESTS", "campaigns")`, источник `(836, "FORTESTS")`; списки — публичные атрибуты `offers`, `domains`, `groups`, `traffic_sources`, их можно менять в тесте;
    - `campaigns: dict[int, KeitaroCampaign]`, `streams: dict[int, KeitaroStream]` — состояние; id выдаются по возрастанию; `create_campaign` возвращает кампанию с `domain=fake.campaign_domain` (атрибут, по умолчанию `"https://kylovoa.com/"`; `None` — ответ без домена); `archive_*` ставят `state="deleted"`; `list_campaigns` и `get_campaign_streams` не отдают архивные (как Keitaro, В7);
    - `calls: list[tuple]` — журнал вызовов: `("create_campaign", alias)`, `("create_country_redirect_stream", NewCountryRedirectStream)`, `("create_offers_stream", NewOffersStream)`, `("archive_stream", id)`, `("archive_campaign", id)`, `("list_offers",)` и т. п. — для проверки порядка;
    - `fail(method: str, error: Exception, *, times: int = 1, after_applying: bool = False) -> None` — следующие `times` вызовов `method` бросают `error`; `after_applying=True` — сначала применить изменение (объект создан), потом бросить: так моделируется таймаут ответа, когда Keitaro уже создал объект.

- [ ] **Step 1: Тесты стран**

```python
def test_countries_are_iso_alpha2_sorted_by_name():
    countries = list_countries()
    assert len(countries) >= 249
    assert all(len(c.code) == 2 and c.code.isupper() for c in countries)
    assert [c.name for c in countries] == sorted(c.name for c in countries)

def test_find_country_ignores_case_and_spaces():
    assert find_country(" de ") == Country("DE", "Germany")
    assert find_country("XX") is None
```

- [ ] **Step 2: Тесты каталога офферов** (`FakeKeitaroClient` с офферами `18813 "Test offer 18813"`, `20001 "Flexacil PE"`, `18800 "Other"`; часы — список-счётчик)

```python
def test_search_by_id_prefix_puts_exact_id_first(): ...
    # search("18813") → [18813]; search("188") → [18813, 18800] (порядок Keitaro)
def test_search_text_query_matches_name_case_insensitively(): ...
    # search("flexacil") → [20001]
def test_search_blank_query_returns_first_offers(): ...
    # search("   ", limit=2) → первые два по порядку Keitaro
def test_offers_are_cached_for_ttl(): ...
    # два search в пределах TTL → один ("list_offers",) в calls; после сдвига часов > TTL → два
def test_find_refreshes_once_on_miss(): ...
    # кэш свежий, оффер 30000 добавлен в fake.offers → find(30000) находит его;
    # find(99999) → None и ровно одно дополнительное обращение list_offers
```

- [ ] **Step 3: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_countries.py tests/test_offer_catalog.py -q`

- [ ] **Step 4: Реализовать** `countries.py`, `offer_catalog.py`, `tests/fakes.py`. Если в pycountry у страны есть `common_name` — использовать название ISO `name` всё равно (стабильно и совпадает с ISO).

- [ ] **Step 5: Запустить все тесты — проходят.**

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/domain backend/app/services backend/tests/fakes.py backend/tests/test_countries.py backend/tests/test_offer_catalog.py
git commit -m "Справочники создаватора: страны ISO 3166-1 и каталог офферов с кэшем"
```

---

### Task 4: Создаватор — проверки и создание кампании

**Files:**
- Create: `backend/app/core/errors.py`, `backend/app/domain/alias.py`, `backend/app/services/creator_references.py`, `backend/app/services/campaign_creator.py`
- Modify: `backend/app/keitaro/errors.py` (`KeitaroError(AppError)`; конструктор и атрибуты прежние)
- Test: `backend/tests/test_alias.py`, `backend/tests/test_creator_references.py`, `backend/tests/test_campaign_creator.py`

**Interfaces:**
- Consumes: `FakeKeitaroClient`, `OfferCatalog`, `find_country` (Task 3); `CreatedCampaignsRepository`, `CreationStatus`, `db_session` (Task 2); `find_reference` (`app/keitaro/references.py`); модели `NewCampaign`, `NewCountryRedirectStream`, `NewOffersStream`, `StreamOfferShare`.
- Produces:
  - `app.core.errors.AppError(Exception)`: атрибуты класса `code = "app_error"`, `http_status = 500`; `__init__(message: str)`, поле `message`.
  - `app.domain.alias`: `ALIAS_LENGTH = 6`; `generate_alias() -> str` — `secrets.choice` из `string.ascii_letters + string.digits`.
  - `app.services.creator_references`:
    - `CreatorMisconfiguredError(AppError)`: `code = "creator_misconfigured"`, `http_status = 503`.
    - `CreatorReferences(domain_id: int, domain_name: str, group_id: int, traffic_source_id: int)` — frozen dataclass.
    - `CreatorReferenceResolver(client: KeitaroClient, settings: Settings)`, `resolve() -> CreatorReferences`: разрешает `CAMPAIGN_DOMAIN`/`CAMPAIGN_GROUP`/`CAMPAIGN_TRAFFIC_SOURCE` через `find_reference` по `list_domains()`/`list_campaign_groups()`/`list_traffic_sources()`; успешный результат кэшируется (повторный `resolve` в Keitaro не ходит); неудача не кэшируется. Все проблемы — одним сообщением через `"; "`: пустая настройка → `"CAMPAIGN_DOMAIN не задан"`, не найдено → `"CAMPAIGN_DOMAIN=kylovoa.org не найден в Keitaro"`.
  - `app.services.campaign_creator`:
    - ошибки (`AppError`): `InvalidCampaignNameError` (`"invalid_name"`, 422, `"Название кампании не может быть пустым"`), `NamePrefixRequiredError` (`"name_prefix_required"`, 422, `f"Название кампании должно начинаться с «{prefix}»"` — 422, а не 403 из дизайна 5.6, потому что это ошибка ввода в форме, дизайн 4.1), `UnknownCountryError` (`"unknown_country"`, 422, `f"Неизвестный код страны: {code}"`), `OfferNotFoundError` (`"offer_not_found"`, 422, `f"Оффер {offer_id} не найден в Keitaro"`), `CampaignCreationFailedError(message: str, code: str, http_status: int)` — код и статус задаются экземпляром (используется в Task 5).
    - константы: `MAX_ALIAS_ATTEMPTS = 3`, `COUNTRY_STREAM_NAME = "Flow 1"`, `OFFERS_STREAM_NAME = "Flow 2"`, `FULL_SHARE = 100`.
    - `CampaignRequest(name: str, country: str, offer_id: int)` — frozen dataclass, вход сервиса.
    - `CampaignCreator(client: KeitaroClient, offers: OfferCatalog, references: CreatorReferenceResolver, settings: Settings, generate_alias: Callable[[], str] = generate_alias)`, метод `create(journal: CreatedCampaignsRepository, request: CampaignRequest) -> CreatedCampaign`.

Порядок `create` (всё до шага 6 — без записи в Keitaro и без строки журнала):
1. `name = request.name.strip()`; пусто → `InvalidCampaignNameError`.
2. Префикс задан и `name` с него не начинается → `NamePrefixRequiredError`.
3. `find_country(request.country)` → `None` → `UnknownCountryError(request.country.strip())`; дальше используется `country.code`.
4. `references.resolve()`.
5. `offers.find(request.offer_id)` → `None` → `OfferNotFoundError`.
6. `journal.add_pending(name, country.code, offer_id)`.
7. `create_campaign(NewCampaign(name, alias, ...))` с новым alias на каждую попытку; `KeitaroAliasTakenError` → следующая попытка, не больше `MAX_ALIAS_ATTEMPTS` (исчерпание — Task 5). Сохранить в журнал `alias`, `keitaro_campaign_id`.
8. Flow 1: `NewCountryRedirectStream(campaign_id, COUNTRY_STREAM_NAME, position=1, country_code, settings.redirect_url)` → `country_stream_id` в журнал.
9. Flow 2: `NewOffersStream(campaign_id, OFFERS_STREAM_NAME, position=2, offers=(StreamOfferShare(offer_id, FULL_SHARE),))` → `offers_stream_id` в журнал.
10. `campaign_url = f"{base.rstrip('/')}/{alias}"`, где `base` — `domain` из ответа на создание кампании, а если его нет — `f"https://{references.domain_name}"`; статус `created`, `save`, вернуть строку журнала.

Каждый шаг 7–9 сохраняет журнал сразу после успеха: если процесс упадёт, в журнале останутся id для ручной уборки.

- [ ] **Step 1: Тесты alias и справочников**

```python
def test_alias_is_six_letters_or_digits():
    aliases = {generate_alias() for _ in range(50)}
    assert all(len(a) == 6 and a.isascii() and a.isalnum() for a in aliases) and len(aliases) > 1

def test_resolver_finds_ids_by_name_and_caches(make_settings): ...
    # FORTESTS/kylovoa.com → CreatorReferences(1813, "kylovoa.com", 10332, 836);
    # второй resolve() не добавляет вызовов в fake.calls
def test_resolver_accepts_numeric_ids(make_settings): ...
    # CAMPAIGN_DOMAIN="1813" и т. д. → те же id
def test_resolver_reports_every_missing_reference(make_settings):
    settings = make_settings(campaign_domain="kylovoa.org", campaign_group="FORTESTS",
                             campaign_traffic_source="")
    with pytest.raises(CreatorMisconfiguredError) as error:
        CreatorReferenceResolver(FakeKeitaroClient(), settings).resolve()
    assert error.value.message == ("CAMPAIGN_DOMAIN=kylovoa.org не найден в Keitaro; "
                                   "CAMPAIGN_TRAFFIC_SOURCE не задан")
```

- [ ] **Step 2: Тесты создаватора** — `test_campaign_creator.py`. Фикстура собирает `CampaignCreator` на `FakeKeitaroClient`, `OfferCatalog(fake, ttl_seconds=300)`, резолвере и `make_settings(keitaro_write_name_prefix="test_oso4lq_", campaign_domain="kylovoa.com", campaign_group="FORTESTS", campaign_traffic_source="FORTESTS")`, генератор alias — итератор `"alias1", "alias2", ...`; журнал — `CreatedCampaignsRepository(db_session)`.

```python
def test_creates_campaign_with_country_stream_first(creator, fake, journal):
    entry = creator.create(journal, CampaignRequest("test_oso4lq_one", "DE", 18813))
    writes = [call for call in fake.calls if call[0].startswith("create")]
    assert [call[0] for call in writes] == [
        "create_campaign", "create_country_redirect_stream", "create_offers_stream"]
    country_stream, offers_stream = writes[1][1], writes[2][1]
    assert (country_stream.position, country_stream.country_code,
            country_stream.redirect_url) == (1, "DE", "https://google.com")
    assert (offers_stream.position, offers_stream.offers) == (2, (StreamOfferShare(18813, 100),))
    assert entry.status == CreationStatus.CREATED and entry.alias == "alias1"
    assert entry.campaign_url == "https://kylovoa.com/alias1"
    assert entry.country_stream_id and entry.offers_stream_id and entry.keitaro_campaign_id

def test_alias_taken_retries_with_new_alias(creator, fake, journal): ...
    # fake.fail("create_campaign", KeitaroAliasTakenError("taken", 422, frozenset({"alias"})))
    # → entry.alias == "alias2", два ("create_campaign", ...) в calls

@pytest.mark.parametrize(("request_", "error_class"), [
    (CampaignRequest("   ", "DE", 18813), InvalidCampaignNameError),
    (CampaignRequest("other_campaign", "DE", 18813), NamePrefixRequiredError),
    (CampaignRequest("test_oso4lq_x", "XX", 18813), UnknownCountryError),
    (CampaignRequest("test_oso4lq_x", "DE", 99999), OfferNotFoundError),
])
def test_invalid_input_is_rejected_before_any_write(creator, fake, journal, request_, error_class):
    with pytest.raises(error_class):
        creator.create(journal, request_)
    assert not [c for c in fake.calls if c[0].startswith(("create", "archive"))]
    assert journal.list_recent() == []

def test_misconfigured_references_are_rejected_before_any_write(...): ...
    # campaign_domain="kylovoa.org" → CreatorMisconfiguredError, нет create-вызовов и строк журнала
def test_name_is_trimmed_before_prefix_check(...): ...
    # "  test_oso4lq_x  " → создано, NewCampaign.name == "test_oso4lq_x", entry.name тоже
def test_country_code_is_normalized(...): ...
    # "de" → country_code "DE" в потоке и entry.country == "DE"
def test_keitaro_down_during_validation_writes_nothing(...): ...
    # fake.fail("list_offers", KeitaroUnavailableError("Keitaro недоступен: таймаут"))
    # → KeitaroUnavailableError; нет create-вызовов, журнал пуст
def test_campaign_url_falls_back_to_configured_domain(...): ...
    # fake.campaign_domain = None → campaign_url == "https://kylovoa.com/alias1"
def test_journal_entry_is_pending_before_first_write(...): ...
    # хук: обёртка над fake.create_campaign читает journal.list_recent() в момент вызова
    # → одна строка со статусом pending
```

- [ ] **Step 3: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_alias.py tests/test_creator_references.py tests/test_campaign_creator.py -q`

- [ ] **Step 4: Реализовать** `AppError`, наследование `KeitaroError`, alias, резолвер, `CampaignCreator.create` (без компенсации — ошибки шагов 7–9 пока пробрасываются).

- [ ] **Step 5: Запустить все тесты — проходят** (включая `test_api_errors.py`: наследование не меняет ответы).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/errors.py backend/app/keitaro/errors.py backend/app/domain/alias.py backend/app/services backend/tests/test_alias.py backend/tests/test_creator_references.py backend/tests/test_campaign_creator.py
git commit -m "Создаватор: проверки до записи и создание кампании с двумя потоками"
```

---

### Task 5: Создаватор — компенсация при сбое

**Files:**
- Modify: `backend/app/services/campaign_creator.py`
- Test: `backend/tests/test_campaign_compensation.py`

**Interfaces:**
- Consumes: Task 4 (`CampaignCreator`, `CampaignCreationFailedError`, `MAX_ALIAS_ATTEMPTS`), `FakeKeitaroClient.fail(...)`.
- Produces: `create` при сбое на шагах 7–9 всегда завершает строку журнала статусом `failed` или `compensation_failed` с текстом в `error` и бросает `CampaignCreationFailedError`. Поведение:

| Сбой | Что делаем | Статус журнала | Ошибка API (`code`, статус) |
|---|---|---|---|
| alias занят `MAX_ALIAS_ATTEMPTS` раз | ничего не создано | `failed` | `keitaro_rejected`, 422; текст `"Не удалось подобрать свободный alias за 3 попытки"` |
| `create_campaign`: `KeitaroUnavailableError` (таймаут, 5xx, неразобранный ответ — кампания могла создаться) | ищем кампанию с нашим alias в `list_campaigns()`; нашли → компенсация; не нашли → ничего не создано | `failed` / по итогу компенсации | код и статус исходной ошибки |
| там же, но `list_campaigns()` сам упал | проверить нельзя | `compensation_failed` | `compensation_failed`, 502 |
| `create_campaign`: другая `KeitaroError` (отказ, 401, 403, 404) | ничего не создано | `failed` | код и статус исходной ошибки |
| любая ошибка на Flow 1 / Flow 2 (включая не-`AppError`) | компенсация | `failed` / `compensation_failed` | исходной ошибки; не-`AppError` → `internal_error`, 500, текст `"внутренняя ошибка"` |

Компенсация кампании `campaign_id` с известными потоками `known_stream_ids`: потоки = известные ∪ `get_campaign_streams(campaign_id)` (так ловятся потоки, созданные запросом, ответ на который потерян; если чтение упало — только известные и отметка «список потоков не прочитан»); каждый поток `archive_stream` (ошибка одного не останавливает остальные), затем `archive_campaign`. Успех — ничего не осталось и список потоков прочитан.

Тексты:
- компенсация успешна или убирать нечего: `error = f"Кампания не создана: {cause.message}"` + (если что-то убрано) `". Созданное в Keitaro перенесено в архив"`;
- компенсация не удалась: `f"Кампания не создана: {cause.message}. Не удалось убрать в архив: {остатки} — нужна ручная уборка (журнал #{entry.id})"`, где остатки перечисляют `кампания {id}`, `потоки {ids}` и/или `список потоков не прочитан`.

Сообщение API = `error` журнала.

- [ ] **Step 1: Тесты** — `test_campaign_compensation.py` (фикстуры как в Task 4; общие фикстуры вынести в `conftest.py` или общий модуль, не копировать)

```python
def test_failure_on_country_stream_archives_campaign(creator, fake, journal):
    fake.fail("create_country_redirect_stream", KeitaroRejectedError("Keitaro отклонил запрос: x", 422))
    with pytest.raises(CampaignCreationFailedError) as error:
        creator.create(journal, CampaignRequest("test_oso4lq_c", "DE", 18813))
    assert (error.value.code, error.value.http_status) == ("keitaro_rejected", 422)
    [entry] = journal.list_recent()
    assert entry.status == CreationStatus.FAILED and entry.error == error.value.message
    assert ("archive_campaign", entry.keitaro_campaign_id) in fake.calls
    assert fake.campaigns[entry.keitaro_campaign_id].state == "deleted"

def test_failure_on_offers_stream_archives_streams_before_campaign(...): ...
    # fake.fail("create_offers_stream", KeitaroUnavailableError(...), after_applying=True)
    # → archive_stream для Flow 1 и для Flow 2 (найден через get_campaign_streams),
    #   оба раньше archive_campaign в fake.calls; статус failed; код keitaro_unavailable, 502
def test_lost_campaign_response_is_found_by_alias_and_archived(...): ...
    # fake.fail("create_campaign", KeitaroUnavailableError(...), after_applying=True)
    # → archive_campaign(id кампании с alias "alias1"); статус failed
def test_campaign_not_created_means_nothing_to_archive(...): ...
    # fake.fail("create_campaign", KeitaroUnavailableError(...)) → нет archive-вызовов,
    # error == "Кампания не создана: <текст>", статус failed
def test_alias_taken_every_time_fails_without_writes(...): ...
    # fake.fail("create_campaign", KeitaroAliasTakenError(...), times=3)
    # → ровно 3 create_campaign, нет archive; keitaro_rejected/422; текст про 3 попытки
def test_rejected_campaign_is_not_compensated(...): ...
    # KeitaroForbiddenError на create_campaign → keitaro_forbidden/403, нет list_campaigns и archive
def test_failed_compensation_is_recorded_for_manual_cleanup(...):
    # Flow 2 падает, archive_campaign тоже падает
    # → статус compensation_failed; error содержит f"кампания {campaign_id}" и f"журнал #{entry.id}";
    #   code compensation_failed, 502
def test_alias_lookup_failure_is_reported_as_compensation_failed(...): ...
    # create_campaign: Unavailable, list_campaigns: Unavailable → compensation_failed
def test_unexpected_error_is_compensated_and_reported_as_internal(...): ...
    # fake.fail("create_offers_stream", RuntimeError("boom")) → archive вызваны;
    # code internal_error, 500; "boom" нет в сообщении
```

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_campaign_compensation.py -q`

- [ ] **Step 3: Реализовать** компенсацию в `campaign_creator.py` (отдельные методы: поиск кампании по alias, компенсация, завершение журнала с ошибкой).

- [ ] **Step 4: Запустить все тесты — проходят.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/campaign_creator.py backend/tests
git commit -m "Создаватор: компенсация частично созданного и запись сбоя в журнал"
```

---

### Task 6: API создаватора и справочников

**Files:**
- Create: `backend/app/schemas/__init__.py`, `backend/app/schemas/creator.py`, `backend/app/schemas/catalog.py`, `backend/app/api/dependencies.py`, `backend/app/api/creator.py`, `backend/app/api/catalog.py`
- Modify: `backend/app/main.py`, `backend/app/api/errors.py`
- Test: `backend/tests/test_api_creator.py`, `backend/tests/test_api_catalog.py`, `backend/tests/test_api_errors.py`

**Interfaces:**
- Consumes: Task 2–5.
- Produces:
  - `create_app(settings: Settings | None = None, keitaro_client: KeitaroClient | None = None) -> FastAPI` — без клиента строит `KeitaroHttpClient.from_settings(settings)` (сети при этом нет); в `app.state`: `settings`, `engine`, `session_factory`, `keitaro_client`, `offer_catalog` (`OfferCatalog(client, settings.offers_cache_ttl_seconds)`), `campaign_creator`; `lifespan` закрывает клиент при остановке.
  - `register_error_handlers`: один обработчик `AppError` → `JSONResponse(status_code=exc.http_status, content={"code": exc.code, "message": exc.message})` (покрывает и `KeitaroError`).
  - `app.api.dependencies`: `get_db_session(request) -> Iterator[Session]`, `get_campaign_creator(request) -> CampaignCreator`, `get_offer_catalog(request) -> OfferCatalog`.
  - Схемы (Pydantic, свои, не копия Keitaro):
    - `CampaignCreateRequest(name: str, country: str, offer_id: int)`;
    - `CreatedCampaignResponse(journal_id: int, keitaro_campaign_id: int, name: str, alias: str, campaign_url: str, country: str, offer_id: int, country_stream_id: int, offers_stream_id: int)`;
    - `JournalEntryResponse(id: int, name: str, alias: str | None, country: str, offer_id: int, status: str, keitaro_campaign_id: int | None, country_stream_id: int | None, offers_stream_id: int | None, campaign_url: str | None, error: str | None, created_at: datetime, updated_at: datetime)`;
    - `OfferResponse(id: int, name: str)`, `CountryResponse(code: str, name: str)`.
  - Эндпоинты:
    - `POST /api/campaigns` → 201 `CreatedCampaignResponse`; ошибки — `{code, message}`;
    - `GET /api/created-campaigns` → `list[JournalEntryResponse]`, новые первыми;
    - `GET /api/offers?query=` (по умолчанию `""`) → `list[OfferResponse]` (до 20);
    - `GET /api/countries` → `list[CountryResponse]`.

- [ ] **Step 1: Тесты** — фикстура `api` в `test_api_creator.py`: `create_app(make_settings(keitaro_write_name_prefix="test_oso4lq_", campaign_domain="kylovoa.com", campaign_group="FORTESTS", campaign_traffic_source="FORTESTS"), keitaro_client=fake)`, `Base.metadata.create_all(app.state.engine)`, `TestClient(app)`.

```python
def test_create_campaign_returns_what_was_created(api):
    response = api.post("/api/campaigns",
                        json={"name": "test_oso4lq_api", "country": "de", "offer_id": 18813})
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["country"], body["offer_id"]) == ("test_oso4lq_api", "DE", 18813)
    assert body["campaign_url"] == f"https://kylovoa.com/{body['alias']}"

def test_create_campaign_validation_error_has_code_and_message(api):
    response = api.post("/api/campaigns",
                        json={"name": "test_oso4lq_api", "country": "XX", "offer_id": 18813})
    assert response.status_code == 422
    assert response.json() == {"code": "unknown_country", "message": "Неизвестный код страны: XX"}

def test_keitaro_failure_during_creation_is_not_500(api, fake): ...
    # fake.fail("create_offers_stream", KeitaroRejectedError("Keitaro отклонил запрос: x", 422))
    # → 422, code keitaro_rejected, message начинается с "Кампания не создана"
def test_journal_lists_created_and_failed_newest_first(api, fake): ...
    # одна успешная, одна с отказом → статусы ["failed", "created"]
def test_misconfigured_creator_answers_503(...): ...
    # campaign_group="NOPE" → 503, code creator_misconfigured
```

`test_api_catalog.py`: `test_offers_search_returns_id_and_name` (`?query=188` → `[{"id": 18813, "name": "Test offer 18813"}]`), `test_countries_include_germany` (`{"code": "DE", "name": "Germany"}` в списке), `test_offers_search_reports_keitaro_down` (502, `keitaro_unavailable`).

`test_api_errors.py`: + `test_app_error_becomes_json_response` (произвольный `AppError` с `code="x"`, `http_status=418`) и `test_create_app_keeps_http_library_logs_clamped` (после `create_app` уровни `httpx` и `httpcore` — `WARNING`).

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_api_creator.py tests/test_api_catalog.py tests/test_api_errors.py -q`

- [ ] **Step 3: Реализовать** схемы, зависимости, роутеры (роутеры только переводят HTTP ↔ сервис), `create_app`, обработчик ошибок.

- [ ] **Step 4: Запустить все тесты и линтер — зелёные.** Run: `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "API создаватора: создание кампании, журнал, поиск офферов, список стран"
```

---

### Task 7: Инструменты приёмки — сравнение кампаний и уборка тестовых

**Files:**
- Create: `backend/tools/compare_campaigns.py`, `backend/tools/archive_test_campaign.py`
- Test: `backend/tests/test_compare_campaigns.py`, `backend/tests/test_archive_test_campaign.py`

**Interfaces:**
- Consumes: примеры 22, 23, 24; `tools.keitaro_examples` (`sanitize`, `write_example`, `EXAMPLES_DIR`); `KeitaroHttpSession` (сырые ответы — модели клиента отбрасывают поля, а сравнивать надо все); `FakeKeitaroClient`.
- Produces:
  - `tools.compare_campaigns`:
    - `CAMPAIGN_IGNORED_FIELDS = {"id", "alias", "name", "token", "created_at", "updated_at"}` — у кампании; `NESTED_IGNORED_FIELDS = {"id", "campaign_id", "stream_id", "oid", "created_at", "updated_at"}` — в потоках и вложенных фильтрах/офферах (имя потока и фильтра сравнивается).
    - `campaign_differences(reference_campaign: dict, reference_streams: list[dict], candidate_campaign: dict, candidate_streams: list[dict]) -> list[str]` — потоки сопоставляются по `position`; путь — `campaign.<поле>`, `stream <position>.<поле>`, вложенное — `stream 1.filters[0].payload`; строка: `f"{path}: эталон {ref!r}, проверяемая {cand!r}"`, отсутствующее поле — `f"{path}: нет в проверяемой"` / `f"{path}: нет в эталоне"`; поток без пары — `f"stream {position}: нет в проверяемой"` (или в эталоне).
    - `main(argv: list[str] | None = None, *, load_settings=Settings, build_session=KeitaroHttpSession.from_settings) -> int` — `python -m tools.compare_campaigns REFERENCE_ID CANDIDATE_ID [--record NAME]`; читает `GET /campaigns/{id}` и `GET /campaigns/{id}/streams`; печатает различия или `"Расхождений нет"`; код 0 — нет различий, 1 — есть или ошибка Keitaro (текст ошибки, без трейсбека), 2 — ошибка конфигурации (только имена переменных). `--record NAME` пишет `docs/keitaro-examples/NAME.json`: `request` — `GET /campaigns/{candidate_id}`, `response` — проверяемая кампания, `observations` — `reference` (кампания и потоки), `candidate_streams`, `differences`; всё через `sanitize` (адрес трекера → `tracker.example.com`, ключ → `***`), `token` обеих кампаний → `"***"`.
  - `tools.archive_test_campaign`: `main(argv: list[str] | None = None, *, load_settings=Settings, build_client=KeitaroHttpClient.from_settings) -> int` — `python -m tools.archive_test_campaign CAMPAIGN_ID --confirm`; без `--confirm`, без `KEITARO_WRITE_NAME_PREFIX` или если имя кампании (`get_campaign`) не начинается с префикса — отказ, код 3, ни одной записи; иначе `archive_stream` каждого потока из `get_campaign_streams`, затем `archive_campaign`; печатает id убранного; код 0.

- [ ] **Step 1: Тесты сравнения** (на реальных записанных данных)

```python
def test_admin_reference_matches_admin_default_bodies(keitaro_example):
    reference, checked = keitaro_example("23-get-admin-reference-campaign"), keitaro_example("24-create-campaign-admin-defaults")
    assert campaign_differences(reference["response"]["body"], reference["observations"]["streams"],
                                checked["observations"]["campaign_after"],
                                checked["observations"]["streams_after"]) == []

def test_api_created_campaign_differs_in_admin_defaults(keitaro_example):
    reference, archived = keitaro_example("23-get-admin-reference-campaign"), keitaro_example("22-delete-campaign")
    differences = campaign_differences(
        reference["response"]["body"], reference["observations"]["streams"],
        archived["response"]["body"][0], archived["observations"]["campaign_streams_after"]["body"])
    assert {line.split(":")[0] for line in differences} == {
        "campaign.uniqueness_method", "campaign.cost_auto", "campaign.notes",
        "campaign.uniqueness_param", "campaign.state",
        "stream 1.weight", "stream 1.comments", "stream 2.weight", "stream 2.comments"}

def test_missing_stream_is_reported(): ...
def test_main_records_sanitized_example(tmp_path, make_settings, monkeypatch): ...
    # build_session → KeitaroHttpSession с MockTransport: по пути отдаёт кампанию и потоки
    # примера 23 на оба id, у кампании token="tok-secret"; tools.compare_campaigns.EXAMPLES_DIR
    # подменён на tmp_path; код 0, вывод "Расхождений нет"; в записанном файле нет
    # "tok-secret" и "test-secret-key-123"
```

- [ ] **Step 2: Тесты уборки** (`FakeKeitaroClient` с кампанией `test_oso4lq_x` и двумя потоками)

```python
def test_archives_streams_before_campaign(make_settings): ...
    # код 0; в fake.calls archive_stream ×2, затем archive_campaign
def test_refuses_foreign_campaign(make_settings): ...
    # кампания "someone_else" → код 3, нет archive-вызовов
def test_refuses_without_confirm_or_prefix(make_settings): ...
    # без --confirm → 3; keitaro_write_name_prefix="" → 3; нет archive-вызовов
```

- [ ] **Step 3: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_compare_campaigns.py tests/test_archive_test_campaign.py -q`

- [ ] **Step 4: Реализовать** оба инструмента (UTF-8 вывод и сообщение об ошибке конфигурации — как в `app/cli/recon.py`).

- [ ] **Step 5: Запустить все тесты и линтер — зелёные.**

- [ ] **Step 6: Commit**

```bash
git add backend/tools/compare_campaigns.py backend/tools/archive_test_campaign.py backend/tests/test_compare_campaigns.py backend/tests/test_archive_test_campaign.py
git commit -m "Инструменты приёмки: сравнение кампаний поле за полем и уборка тестовой кампании"
```

---

### Task 8: Приёмка на реальном Keitaro и журнал решений

**Files:**
- Create: `docs/keitaro-examples/25-creator-vs-reference.json` (записывает инструмент)
- Modify: `docs/keitaro-examples/README.md`, `docs/decisions.md`

Все команды — из `backend/`, с реальным `.env`. Запись в Keitaro — только шаги 4 и 7.

- [ ] **Step 1: Миграции на рабочую БД.** Run: `.venv/Scripts/python -m alembic upgrade head` → голова `0002`.

- [ ] **Step 2: Запустить бэкенд** (в фоне): `.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000`. Проверить в логе сервера, что нет адреса трекера и ключа.

- [ ] **Step 3: Справочники.** `curl -s "http://localhost:8000/api/countries"` содержит `{"code":"DE","name":"Germany"}`; `curl -s "http://localhost:8000/api/offers?query=18813"` → один оффер 18813.

- [ ] **Step 4: Создать кампанию через нашу API.**

```bash
curl -s -X POST http://localhost:8000/api/campaigns -H "Content-Type: application/json" \
  -d '{"name": "test_oso4lq_creator_check", "country": "DE", "offer_id": 18813}'
```
Expected: 201, `campaign_url` = `https://kylovoa.com/<alias>`; запомнить `keitaro_campaign_id`. `GET /api/created-campaigns` → верхняя запись `created`.

- [ ] **Step 5: Сравнить с эталоном.** Run: `.venv/Scripts/python -m tools.compare_campaigns 215193 <keitaro_campaign_id> --record 25-creator-vs-reference`
Expected: `Расхождений нет`, код 0. Если различия есть — остановиться: устранить (новое поле в теле — только после проверки реальным запросом) или записать в `docs/decisions.md` с причиной и согласовать с владельцем.

- [ ] **Step 6: Проверка примера на утечки.** Run: `.venv/Scripts/python -m pytest tests/test_keitaro_examples.py -q` — зелёный; `grep -c "<адрес трекера из .env>" ../docs/keitaro-examples/25-creator-vs-reference.json` → 0 (адрес подставить из `.env`, в коммит не писать).

- [ ] **Step 7: Убрать обе тестовые кампании в архив.**

```bash
.venv/Scripts/python -m tools.archive_test_campaign <keitaro_campaign_id> --confirm
.venv/Scripts/python -m tools.archive_test_campaign 215193 --confirm
```
Проверка: `GET /campaigns/{id}` обеих → 404, их потоки (`GET /streams/{id}`) → `state: deleted` (одноразовый скрипт через `KeitaroHttpSession`, как при разведке).

- [ ] **Step 8: Остановить бэкенд.**

- [ ] **Step 9: Документация.** `docs/keitaro-examples/README.md` — строка про 25. `docs/decisions.md`, раздел «этап 2» — решения этапа:
  - приёмка: создаватор совпал с эталоном поле за полем (25), обе кампании в архиве;
  - список стран — pycountry (ISO 3166-1 alpha-2, английские названия), а не своя таблица;
  - поиск офферов: префикс id или подстрока названия без учёта регистра, точный id первым, до 20 результатов, кэш `OFFERS_CACHE_TTL_SECONDS`, при промахе `find` — одно обновление;
  - журнал: статусы `pending/created/failed/compensation_failed`, два столбца потоков вместо списка;
  - ответы ошибок: коды и статусы создаватора (`invalid_name`, `name_prefix_required` — 422, а не 403; `unknown_country`, `offer_not_found`, `creator_misconfigured` — 503, `compensation_failed` — 502, `internal_error` — 500);
  - компенсация: поиск кампании по alias при неоднозначном ответе, все потоки кампании через `get_campaign_streams`, порядок «потоки → кампания».

- [ ] **Step 10: Commit**

```bash
git add docs/keitaro-examples docs/decisions.md
git commit -m "Приёмка создаватора: кампания совпадает с эталоном из админки"
```

---

## Проверка готовности этапа

- [ ] `cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` — всё зелёное.
- [ ] `alembic downgrade base` и `alembic upgrade head` на временной БД работают (покрыто `test_migrations.py`).
- [ ] Кампания `test_oso4lq_creator_check`, созданная через `POST /api/campaigns`, совпала с эталоном 215193 без расхождений (пример 25); обе кампании и их потоки в архиве; `clean_archive` не вызывался.
- [ ] Во всех файлах из `git ls-files` нет ключа и адреса трекера (проверка-счётчик по `git ls-files`, как на этапе 1).
- [ ] `docs/decisions.md` — раздел «этап 2» полный; `docs/keitaro-examples/README.md` — строки 23–25.
- [ ] `git status` чистый; push — после подтверждения владельца.
- [ ] В итоговом сообщении этапа — расхождения админки с API и как они закрыты, решения этапа (страны, поиск офферов, коды ошибок, компенсация), что эталон и проверочная кампания в архиве.
