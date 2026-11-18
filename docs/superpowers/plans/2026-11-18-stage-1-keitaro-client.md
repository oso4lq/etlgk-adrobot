# Этап 1 — клиент Keitaro и разведка. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Проверенные на реальном Keitaro примеры запросов в `docs/keitaro-examples/` и ответы на открытые вопросы о `PUT /streams` в `docs/decisions.md`. Клиент Keitaro: транспорт с таймаутами, повторами и понятными ошибками, а также типизированные методы чтения и записи за интерфейсом. Команда `python -m app.cli.recon`, которая показывает домены, группы, источники и офферы реального Keitaro.

**Architecture:** Сначала разведка: скрипт `backend/tools/keitaro_probe.py` на голом httpx фиксирует поведение самого Keitaro (а не нашего клиента) и сохраняет очищенные от секретов пары «запрос–ответ». Затем пакет `app/keitaro/`: `errors.py` (исключения с кодом и HTTP-статусом нашей API), `http_session.py` (`KeitaroHttpSession` — ключ, таймауты, повторы, разбор ошибок), `models.py` (модели ответов и входные dataclass-ы), `client.py` (Protocol `KeitaroClient` + `KeitaroHttpClient` — единственное место, знающее формат тел Keitaro), `references.py`. Тесты клиента отвечают записанными реальными ответами и сверяют отправленные тела с теми, что Keitaro принял при разведке. Обработчик FastAPI превращает `KeitaroError` в `{code, message}`.

**Tech Stack:** Python ≥3.12, httpx (`httpx.Client`, `httpx.MockTransport` в тестах), Pydantic v2, FastAPI, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-18-adrobot-design.md` — разделы 3.2, 4.2, 4.3 (п. 6), 5.3 (Push), 6.1, 6.2, 9 («Этап 1»); правила — `CLAUDE.md`, разделы 1, 7, 9, 10.

## Global Constraints

- Не выдумывать API Keitaro: пути и поля — только из `docs/keitaro-openapi.json` или из реального ответа. Расхождение схемы с реальностью → приоритет у реального ответа, запись в `docs/decisions.md`.
- Запись в реальный Keitaro — только в Task 1 и только объекты, созданные в этом же запуске, с именем на `test_oso4lq_`. `clean_archive` не вызывать никогда. Не делать `PUT`/`DELETE` по id, созданным не нами в этом запуске.
- Секреты — ключ API **и адрес трекера** (`CLAUDE.md`, раздел 1). Их нет в логах, сообщениях об ошибках, ответах нашей API, `docs/keitaro-examples/` и коммитах. В примерах адрес трекера заменяется на `tracker.example.com`, а ключ — на `***`.
- Списки чужих объектов в примеры не попадают: сохраняются только элементы с нашими id (оффер 18813, домен 1813, группа 10332, источник 836, созданные нами кампании и потоки).
- Повторы: GET повторяется при сетевых ошибках, таймаутах и ответах 502/503/504. Запросы на запись (POST/PUT/DELETE) повторяются **только** если соединение не установлено (`httpx.ConnectError`, `httpx.ConnectTimeout`), иначе возможны дубли. Число повторов — `KEITARO_MAX_RETRIES` (дополнительные попытки сверх первой), таймаут — `KEITARO_TIMEOUT_SECONDS`.
- Маппинг ошибок (дизайн 6.2): сеть/таймаут/5xx → 502 `keitaro_unavailable`; 401 → 502 `keitaro_auth_failed`; 402 → 502 `keitaro_license`; 403 → 403 `keitaro_forbidden`; 404 → 404 `keitaro_not_found`; 400/406/422 и прочие 4xx → 422 `keitaro_rejected` + текст Keitaro.
- Синхронный стек: `httpx.Client`, обычные функции.
- Комментарии объясняют «почему». Коммиты — по-русски, по делу, последняя строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Команды — для Git Bash на Windows (`.venv/Scripts/python`); путь репозитория содержит пробел.

## Факты, проверенные при планировании (только чтение, 2026-11-18)

- Потоки с офферами на этом инстансе: `schema=landings`, `action_type=http`, `action_payload=null`. Поток «страна → URL»: `schema=redirect`, `action_type=http`, `action_payload="https://..."`. Фильтр в ответе выглядит так: `{"id", "stream_id", "name": "country", "mode": "accept", "payload": ["AU"], "oid"}`.
- `GET /campaigns` без параметров отдаёт все кампании (412), `limit`/`offset` работают. В элементе есть `domain` (`"https://kylovoa.com/"`), `domain_id`, `group`, `group_id`, `traffic_source_id`, `alias`, `type`, `state`.
- Неверный ключ: `401 {"error":"Invalid API key"}`. Несуществующая кампания: `404` с **HTML-страницей nginx**, а не JSON.
- `/stream_types`: `regular`, `default`, `forced`.

## Review Focus

1. **Keitaro отвечает не JSON:** HTML-страница nginx на 404/502, пустое тело на DELETE. Ожидается понятная ошибка без HTML в тексте, а пустой успешный ответ даёт `None`. Тесты: Task 2 `test_html_error_body_is_not_echoed`, `test_empty_success_body_returns_none`.
2. **Таймаут ответа на POST/PUT** (запрос мог дойти до Keitaro). Повтор недопустим, иначе появятся дубли кампаний. Тест: Task 2 `test_write_is_not_retried_after_read_timeout`.
3. **Ключ или адрес трекера утекает в публичный репозиторий** через примеры, логи или сообщения. Тесты: Task 1 `test_committed_examples_reference_only_known_hosts` и тесты очистки; Task 2 `test_api_key_never_leaks`, `test_unavailable_message_hides_tracker_host`; Task 4 `test_output_never_contains_api_key`.
4. **Разведка падает посередине**, и в общем Keitaro остаются активные тестовые объекты. Ожидается уборка всего созданного, даже если одна из уборок упала. Тест: Task 1 `test_archive_all_continues_after_error`.
5. **Команда разведки запущена с неверным ключом или без переменных в `.env`.** Ожидается понятное сообщение без трейсбека и ненулевой код выхода. Тесты: Task 4 `test_main_reports_keitaro_error_without_traceback`, `test_main_reports_missing_settings`.

---

## Структура файлов

```
backend/
  tools/__init__.py
  tools/keitaro_examples.py   — очистка от секретов, отбор своих id, diff полей, запись примеров, уборка созданного
  tools/keitaro_probe.py      — разведка на реальном Keitaro (запускается вручную с --confirm-writes)
  app/keitaro/__init__.py
  app/keitaro/errors.py       — KeitaroError и подклассы (code, http_status, message)
  app/keitaro/http_session.py — KeitaroHttpSession: httpx.Client, Api-Key, таймауты, повторы, разбор ошибок
  app/keitaro/models.py       — модели ответов Keitaro (Pydantic) и входные dataclass-ы
  app/keitaro/client.py       — Protocol KeitaroClient, KeitaroHttpClient
  app/keitaro/references.py   — find_reference(): справочник по имени или id
  app/api/errors.py           — register_error_handlers(app)
  app/cli/__init__.py
  app/cli/recon.py            — python -m app.cli.recon
  tests/test_keitaro_examples.py
  tests/test_keitaro_http_session.py
  tests/test_api_errors.py
  tests/test_keitaro_client.py
  tests/test_recon.py
docs/keitaro-examples/        — NN-<slug>.json + README.md (оглавление)
docs/decisions.md             — раздел «этап 1»
```

---

### Task 1: Разведка реального Keitaro и примеры запросов

**Files:**
- Create: `backend/tools/__init__.py`, `backend/tools/keitaro_examples.py`, `backend/tools/keitaro_probe.py`, `docs/keitaro-examples/*.json`, `docs/keitaro-examples/README.md`
- Modify: `docs/decisions.md`
- Test: `backend/tests/test_keitaro_examples.py`

**Interfaces:**
- Consumes: `app.core.config.Settings`, `REPOSITORY_ROOT`.
- Produces (`tools/keitaro_examples.py`):
  - `EXAMPLES_DIR: Path` (= `REPOSITORY_ROOT / "docs" / "keitaro-examples"`)
  - `sanitize(value: Any, replacements: Mapping[str, str]) -> Any` — рекурсивно заменяет подстроки во всех строковых значениях; пустые ключи замены пропускаются.
  - `keep_only_ids(items: list[dict], allowed_ids: set[int]) -> list[dict]`
  - `changed_fields(before: dict, after: dict, ignore: set[str]) -> dict[str, tuple[Any, Any]]`
  - `write_example(directory: Path, name: str, *, title: str, request: dict, response: dict, observations: dict | None = None) -> Path` — UTF-8, `indent=2`, `ensure_ascii=False`, перевод строки в конце.
  - `@dataclass CreatedObjects(campaign_ids: list[int], stream_ids: list[int])` с методом `archive_all(client: httpx.Client) -> list[str]`: DELETE сначала всех потоков, потом кампаний; ошибку одного удаления записывает в возвращаемый список и продолжает.
- Produces (данные): файлы примеров из таблицы ниже. На них опираются тесты Task 3 — **имена файлов фиксированы**. Формат файла:
  ```json
  {"title": "...",
   "request": {"method": "PUT", "path": "/streams/123", "query": {}, "body": {}},
   "response": {"status": 200, "body": {}},
   "observations": {}}
  ```
  Тело ответа, которое не является JSON, сохраняется строкой, обрезанной до 300 символов. `observations` — необязательные данные проверки (GET до и после, `changed_fields`).

- [ ] **Step 1: Написать падающие тесты** — `backend/tests/test_keitaro_examples.py`

```python
def test_sanitize_replaces_secrets_in_nested_values():
    data = {"url": "https://tracker.real.io/x", "items": [{"note": "key=abc123"}], "count": 5}
    result = sanitize(data, {"tracker.real.io": "tracker.example.com", "abc123": "***"})
    assert result == {"url": "https://tracker.example.com/x", "items": [{"note": "key=***"}], "count": 5}

def test_sanitize_skips_empty_replacement_keys():
    assert sanitize({"text": "value"}, {"": "***"}) == {"text": "value"}

def test_keep_only_ids_drops_foreign_items():
    assert keep_only_ids([{"id": 1, "name": "ours"}, {"id": 2, "name": "foreign"}], {1}) == [
        {"id": 1, "name": "ours"}
    ]

def test_changed_fields_ignores_listed_keys():
    before = {"name": "Probe", "filters": [1], "updated_at": "a", "offers": []}
    after = {"name": "Probe", "filters": [], "updated_at": "b", "offers": [1]}
    assert changed_fields(before, after, ignore={"updated_at", "offers"}) == {"filters": ([1], [])}

def test_write_example_writes_utf8_json(tmp_path):
    path = write_example(tmp_path, "10-create-campaign", title="Создание",
                         request={"method": "POST", "path": "/campaigns", "query": {}, "body": {}},
                         response={"status": 200, "body": {"id": 1}})
    assert path == tmp_path / "10-create-campaign.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["title"] == "Создание" and saved["response"]["body"] == {"id": 1}

def test_archive_all_deletes_streams_before_campaigns():
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={})
    created = CreatedObjects(campaign_ids=[10], stream_ids=[21, 22])
    with httpx.Client(base_url="https://t.example/admin_api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        assert created.archive_all(client) == []
    assert calls == [("DELETE", "/admin_api/v1/streams/21"), ("DELETE", "/admin_api/v1/streams/22"),
                     ("DELETE", "/admin_api/v1/campaigns/10")]

def test_archive_all_continues_after_error():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/streams/21"):
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={})
    created = CreatedObjects(campaign_ids=[10], stream_ids=[21])
    with httpx.Client(base_url="https://t.example/admin_api/v1",
                      transport=httpx.MockTransport(handler)) as client:
        errors = created.archive_all(client)
    assert len(errors) == 1 and "21" in errors[0]
    assert calls[-1] == "/admin_api/v1/campaigns/10"

KNOWN_HOSTS = {"tracker.example.com", "kylovoa.com", "google.com", "www.google.com"}

def test_committed_examples_reference_only_known_hosts():
    # The tracker address is a secret: any unexpected host in committed examples is a leak.
    for path in EXAMPLES_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        hosts = set(re.findall(r"https?://([^/\"'\s:]+)", text))
        assert hosts <= KNOWN_HOSTS, f"{path.name}: {hosts - KNOWN_HOSTS}"
        assert "Api-Key" not in text
```

Если в ответах окажется легитимный внешний хост (например, URL оффера), его можно добавить в `KNOWN_HOSTS`, но только после того, как глазами проверено, что это не адрес трекера.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_examples.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tools'`).

- [ ] **Step 3: Реализовать `backend/tools/__init__.py` (пустой) и `backend/tools/keitaro_examples.py`** по Interfaces.

- [ ] **Step 4: Запустить — тесты проходят**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_examples.py -v`
Expected: 8 passed (тест хостов проходит на пустой папке).

- [ ] **Step 5: Написать `backend/tools/keitaro_probe.py`**

Запуск: `python -m tools.keitaro_probe --confirm-writes`. Без флага, а также при пустом `KEITARO_WRITE_NAME_PREFIX` скрипт отказывается работать (код 2). Скрипт использует голый `httpx.Client(base_url=f"{settings.keitaro_base_url}/admin_api/v1", headers={"Api-Key": key}, timeout=settings.keitaro_timeout_seconds)`. Каждый вызов возвращает `(status, body)` и не бросает исключение на HTTP-ошибках. Перед записью ответ проходит через `sanitize(..., {tracker_host: "tracker.example.com", api_key: "***"})`. Id домена, группы и источника берутся из ответов 02–04: элемент, у которого `name` или `str(id)` равен `CAMPAIGN_DOMAIN` / `CAMPAIGN_GROUP` / `CAMPAIGN_TRAFFIC_SOURCE`. Всё созданное регистрируется в `CreatedObjects`. В `finally` вызывается `archive_all` для всего, что ещё не в архиве, и печатается итоговая проверка: GET каждого созданного id и его `state`. Тестовая страна — `DE`, alias — 6 случайных символов `[A-Za-z0-9]` (`secrets.choice`).

| Файл | Запрос | Что выясняем |
|---|---|---|
| `01-get-offers` | `GET /offers` → `keep_only_ids({18813})` | формат оффера |
| `02-get-domains` | `GET /domains` → только наш домен | формат домена, поле `name` |
| `03-get-campaign-groups` | `GET /groups?type=campaigns` → только наша группа | формат группы |
| `04-get-traffic-sources` | `GET /traffic_sources` → только наш источник | формат источника |
| `05-error-invalid-api-key` | `GET /offers` с ключом `invalid-key-for-probe` | тело 401 |
| `06-error-not-found` | `GET /campaigns/999999999` | тело 404 (ожидается HTML) |
| `10-create-campaign` | `POST /campaigns` `{name: "{prefix}put_check", alias, type: "position", state: "active", domain_id, group_id, traffic_source_id}` | В1 |
| `11-create-campaign-alias-taken` | `POST /campaigns` с тем же alias, `name: "{prefix}alias_conflict"`; при 2xx сразу DELETE | В2 |
| `12-create-stream-country-redirect` | `POST /streams` `{campaign_id, name: "Flow 1", type: "regular", position: 1, schema: "redirect", action_type: "http", action_payload: REDIRECT_URL, filters: [{name: "country", mode: "accept", payload: ["DE"]}], state: "active"}` | В1 |
| `13-create-stream-offers` | `POST /streams` `{campaign_id, name: "Flow 2", type: "regular", position: 2, schema: "landings", action_type: "http", offers: [{offer_id: 18813, share: 100, state: "active"}], state: "active"}` | В1 |
| `14-create-stream-probe` | `POST /streams` как 13, но `name: "Probe"`, `position: 3`, `comments: "probe"`, `filters: [{name: "country", mode: "reject", payload: ["FR"]}]` | поток с фильтром и офферами для В3 |
| `15-get-campaign-streams` | `GET /campaigns/{id}/streams` | формат потоков |
| `16-put-stream-offers-only` | `PUT /streams/{probe}` `{offers: [{offer_id: 18813, share: 100, state: "active"}]}`; observations: `stream_before`/`stream_after` (`GET /streams/{probe}`), `changed_fields(ignore={"updated_at", "offers"})` | В3, В4 (меняется ли id строки оффера) |
| `17-put-stream-offers-share-zero` | то же, `share: 0`; observations как в 16 | В5 |
| `18-put-stream-offers-empty` | `PUT` `{offers: []}`; observations как в 16 | В4, В6 |
| `19-put-stream-offers-restore` | `PUT` `{offers: [{18813, 100, active}]}`; observations как в 16 | возврат оффера |
| `20-get-campaigns` | `GET /campaigns` → только наша кампания; observations: `total_count` | формат для выбора кампании |
| `21-delete-stream` | `DELETE /streams/{probe}`; observations: `GET /streams/{probe}` после | В7 |
| `22-delete-campaign` | `DELETE /campaigns/{id}` (потоки 1 и 2 **не** удаляем заранее); observations: `GET /campaigns/{id}`, `GET /streams/{flow1}`, `GET /campaigns/{id}/streams` после | В7: архивирует ли удаление кампании её потоки |

После каждого PUT скрипт печатает `changed_fields` и офферы до и после. Если какой-то шаг создания (10, 12, 13, 14) получил не 2xx, скрипт прекращает работу, убирает созданное и печатает ответ Keitaro.

- [ ] **Step 6: Запустить разведку на реальном Keitaro**

Run: `cd backend && .venv/Scripts/python -m tools.keitaro_probe --confirm-writes`
Expected: в `docs/keitaro-examples/` 19 файлов (01–06, 10–22). Итоговая проверка печатает `state=deleted` (или 404) для всех созданных id, ошибок уборки нет.

**Условия остановки** (не продолжать к Task 2–4, сообщить владельцу с выдержками из примеров):
- шаги 10/12/13/14 отвергнуты Keitaro — значит, тела эталона неверны;
- в 16 `changed_fields` не пуст (PUT с одними `offers` меняет что-то ещё — фильтры, `comments`, позицию, действие);
- в 18 у потока после PUT остались офферы (PUT не заменяет список целиком) — дизайн Push (5.3) нужно пересмотреть;
- итоговая проверка показывает созданный объект не в архиве и уборка не удалась.

- [ ] **Step 7: Проверить, что в примерах нет секретов**

Run (вывод — только счётчики, без значений):
```bash
cd backend && .venv/Scripts/python -I -c "
import sys, httpx; sys.path.insert(0, '.')
from app.core.config import Settings, REPOSITORY_ROOT
s = Settings(); key = s.keitaro_api_key.get_secret_value(); host = httpx.URL(s.keitaro_base_url).host
files = list((REPOSITORY_ROOT / 'docs' / 'keitaro-examples').glob('*'))
print('files', len(files), 'with secrets', sum(1 for f in files if key in f.read_text('utf-8') or host in f.read_text('utf-8')))"
```
Expected: `files 19 with secrets 0`. Затем `.venv/Scripts/python -m pytest tests/test_keitaro_examples.py -v` → 8 passed (тест хостов теперь проверяет реальные файлы).

- [ ] **Step 8: Записать выводы**

`docs/keitaro-examples/README.md` — оглавление: файл → что показывает (одна строка на файл) и как получено (`python -m tools.keitaro_probe --confirm-writes`, что скрипт создаёт и убирает).

`docs/decisions.md` — новый раздел `## 2026-11-18 — этап 1 (клиент и разведка)`, в нём ответы с указанием файлов-доказательств:
- **В1.** Принимаются ли тела 10/12/13 как есть; какие поля Keitaro подставил сам (по ответам).
- **В2.** Ответ на занятый alias (статус и текст) или «дубль принят» — тогда на этапе 2 нужна своя проверка уникальности.
- **В3.** PUT только с `offers` не меняет остальные поля потока (`changed_fields` пуст).
- **В4.** PUT заменяет список офферов целиком; сохраняется ли id строки оффера.
- **В5.** Принимается ли `share: 0`.
- **В6.** Принимается ли пустой `offers` (нужно для Push потока без активных офферов, дизайн 5.3).
- **В7.** Что возвращают `DELETE /streams` и `DELETE /campaigns` и что после них видно через GET; архивируются ли потоки вместе с кампанией (важно для компенсации на этапе 2).
- Расхождения схемы `docs/keitaro-openapi.json` с реальностью (если найдены).

- [ ] **Step 9: Линтер и тесты**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`
Expected: всё зелёное.

- [ ] **Step 10: Commit**

```bash
git add backend/tools backend/tests/test_keitaro_examples.py docs/keitaro-examples docs/decisions.md
git commit -m "Разведка Keitaro: примеры реальных запросов, семантика PUT /streams"
```

---

### Task 2: Транспорт Keitaro — ключ, таймауты, повторы, понятные ошибки

**Files:**
- Create: `backend/app/keitaro/__init__.py`, `backend/app/keitaro/errors.py`, `backend/app/keitaro/http_session.py`, `backend/app/api/errors.py`
- Modify: `backend/app/main.py` (вызов `register_error_handlers`), `docs/decisions.md`
- Test: `backend/tests/test_keitaro_http_session.py`, `backend/tests/test_api_errors.py`

**Interfaces:**
- Consumes: `Settings` (`keitaro_base_url`, `keitaro_api_key`, `keitaro_timeout_seconds`, `keitaro_max_retries`).
- Produces:
  - `app.keitaro.errors`: `KeitaroError(Exception)` с атрибутами класса `code: str`, `http_status: int` и экземпляра `message: str`, `keitaro_status: int | None`; конструктор `KeitaroError(message: str, keitaro_status: int | None = None)`. Подклассы (code / http_status / сообщение по умолчанию):
    - `KeitaroUnavailableError` — `keitaro_unavailable` / 502 / `"Keitaro недоступен: {причина}"`, причина — `"таймаут"`, `"ошибка сети"` или `"HTTP {status}"`;
    - `KeitaroAuthError` — `keitaro_auth_failed` / 502 / `"Неверный ключ API Keitaro"`;
    - `KeitaroLicenseError` — `keitaro_license` / 502 / `"Admin API недоступен в этой редакции Keitaro"`;
    - `KeitaroForbiddenError` — `keitaro_forbidden` / 403 / `"Нет доступа к объекту в Keitaro"`;
    - `KeitaroNotFoundError` — `keitaro_not_found` / 404 / `"Объект не найден в Keitaro"`;
    - `KeitaroRejectedError` — `keitaro_rejected` / 422 / `"Keitaro отклонил запрос: {текст}"` (без текста — `"Keitaro отклонил запрос"`).
  - `app.keitaro.http_session.KeitaroHttpSession`:
    - `__init__(self, base_url: str, api_key: str, *, timeout_seconds: float, max_retries: int, retry_delay_seconds: float = 0.5, transport: httpx.BaseTransport | None = None)` — запросы идут на `{base_url}/admin_api/v1{path}`;
    - `@classmethod from_settings(cls, settings: Settings, transport: httpx.BaseTransport | None = None) -> KeitaroHttpSession`;
    - `get(path: str, params: Mapping[str, str | int] | None = None) -> Any`, `post(path: str, body: Mapping[str, Any]) -> Any`, `put(path: str, body: Mapping[str, Any]) -> Any`, `delete(path: str) -> Any` — возвращают разобранный JSON или `None` для пустого тела; при ошибке бросают подкласс `KeitaroError`;
    - `close()`, `__enter__`/`__exit__`; `__repr__` без ключа и адреса.
  - Текст Keitaro для `keitaro_rejected`: `{"error": "..."}` → строка; JSON-объект иного вида (406 `{"field": ["msg"]}`) → `"field: msg; ..."`; не-JSON → без текста. Ключ API, если вдруг встретится в тексте, заменяется на `***`.
  - `app.api.errors.register_error_handlers(app: FastAPI) -> None` — `KeitaroError` → `JSONResponse(status_code=exc.http_status, content={"code": exc.code, "message": exc.message})`.

- [ ] **Step 1: Написать падающие тесты транспорта** — `backend/tests/test_keitaro_http_session.py`

```python
API_KEY = "secret-key-123"

def make_session(handler, max_retries=2):
    return KeitaroHttpSession("https://tracker.example.com", API_KEY, timeout_seconds=5,
                              max_retries=max_retries, retry_delay_seconds=0,
                              transport=httpx.MockTransport(handler))

def test_sends_api_key_to_admin_api_path():
    def handler(request):
        assert request.headers["Api-Key"] == API_KEY
        assert str(request.url) == "https://tracker.example.com/admin_api/v1/groups?type=campaigns"
        return httpx.Response(200, json=[{"id": 1}])
    assert make_session(handler).get("/groups", params={"type": "campaigns"}) == [{"id": 1}]

def test_empty_success_body_returns_none():
    assert make_session(lambda request: httpx.Response(201, content=b"")).delete("/streams/1") is None

@pytest.mark.parametrize(("status", "error_class", "code", "http_status"), [
    (401, KeitaroAuthError, "keitaro_auth_failed", 502),
    (402, KeitaroLicenseError, "keitaro_license", 502),
    (403, KeitaroForbiddenError, "keitaro_forbidden", 403),
    (404, KeitaroNotFoundError, "keitaro_not_found", 404),
    (400, KeitaroRejectedError, "keitaro_rejected", 422),
    (406, KeitaroRejectedError, "keitaro_rejected", 422),
    (409, KeitaroRejectedError, "keitaro_rejected", 422),
    (422, KeitaroRejectedError, "keitaro_rejected", 422),
    (500, KeitaroUnavailableError, "keitaro_unavailable", 502),
])
def test_http_errors_are_mapped(status, error_class, code, http_status):
    session = make_session(lambda request: httpx.Response(status, json={"error": "x"}), max_retries=0)
    with pytest.raises(error_class) as error:
        session.get("/offers")
    assert (error.value.code, error.value.http_status, error.value.keitaro_status) == (code, http_status, status)

def test_rejected_message_contains_keitaro_text():
    session = make_session(lambda request: httpx.Response(400, json={"error": "Alias is already taken"}))
    with pytest.raises(KeitaroRejectedError) as error:
        session.post("/campaigns", {"name": "x"})
    assert error.value.message == "Keitaro отклонил запрос: Alias is already taken"

def test_field_errors_are_joined():
    session = make_session(lambda request: httpx.Response(406, json={"name": ["Field is required"]}))
    with pytest.raises(KeitaroRejectedError) as error:
        session.post("/streams", {})
    assert "name: Field is required" in error.value.message

def test_html_error_body_is_not_echoed():
    html = "<html><head><title>404 Not Found</title></head></html>"
    session = make_session(lambda request: httpx.Response(404, text=html, headers={"content-type": "text/html"}))
    with pytest.raises(KeitaroNotFoundError) as error:
        session.get("/campaigns/999999999")
    assert "<html" not in error.value.message

def counting(responses):
    """Handler that plays the given responses/exceptions in order and counts attempts."""
    attempts = []
    def handler(request):
        attempts.append(request.method)
        item = responses[min(len(attempts), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item
    return handler, attempts

def test_get_retries_network_errors_then_succeeds():
    handler, attempts = counting([httpx.ConnectError("down"), httpx.ReadTimeout("slow"), httpx.Response(200, json=[])])
    assert make_session(handler, max_retries=2).get("/offers") == []
    assert len(attempts) == 3

def test_get_gives_up_after_max_retries():
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    with pytest.raises(KeitaroUnavailableError) as error:
        make_session(handler, max_retries=2).get("/offers")
    assert len(attempts) == 3
    assert error.value.message == "Keitaro недоступен: таймаут"

def test_get_retries_on_503():
    handler, attempts = counting([httpx.Response(503), httpx.Response(200, json=[])])
    assert make_session(handler).get("/offers") == []
    assert len(attempts) == 2

def test_write_is_retried_when_connection_failed():
    handler, attempts = counting([httpx.ConnectError("refused"), httpx.Response(200, json={"id": 1})])
    assert make_session(handler).post("/campaigns", {"name": "x"}) == {"id": 1}
    assert len(attempts) == 2

def test_write_is_not_retried_after_read_timeout():
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    with pytest.raises(KeitaroUnavailableError):
        make_session(handler).post("/campaigns", {"name": "x"})
    assert len(attempts) == 1

def test_write_is_not_retried_on_5xx():
    handler, attempts = counting([httpx.Response(503)])
    with pytest.raises(KeitaroUnavailableError):
        make_session(handler).put("/streams/1", {"offers": []})
    assert len(attempts) == 1

def test_api_key_never_leaks(caplog):
    caplog.set_level(logging.DEBUG)
    responses = [httpx.Response(200, json=[]), httpx.Response(401, json={"error": "Invalid API key"})]
    handler, _ = counting(responses)
    session = make_session(handler, max_retries=0)
    session.get("/offers")
    with pytest.raises(KeitaroAuthError) as error:
        session.get("/offers")
    assert API_KEY not in caplog.text
    assert API_KEY not in str(error.value) and API_KEY not in repr(error.value)
    assert API_KEY not in repr(session)

def test_key_echoed_by_keitaro_is_redacted():
    session = make_session(lambda request: httpx.Response(400, json={"error": f"bad key {API_KEY}"}))
    with pytest.raises(KeitaroRejectedError) as error:
        session.get("/offers")
    assert API_KEY not in error.value.message

def test_unavailable_message_hides_tracker_host():
    handler, _ = counting([httpx.ConnectError("cannot connect to tracker.example.com")])
    with pytest.raises(KeitaroUnavailableError) as error:
        make_session(handler, max_retries=0).get("/offers")
    assert "tracker.example.com" not in error.value.message
    assert "tracker.example.com" not in repr(make_session(handler))

def test_from_settings_uses_configured_retries(make_settings):
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    session = KeitaroHttpSession.from_settings(make_settings(keitaro_max_retries=0),
                                               transport=httpx.MockTransport(handler))
    with pytest.raises(KeitaroUnavailableError):
        session.get("/offers")
    assert len(attempts) == 1
```

`backend/tests/test_api_errors.py`:

```python
@pytest.mark.parametrize(("error", "status", "code"), [
    (KeitaroUnavailableError("Keitaro недоступен: таймаут"), 502, "keitaro_unavailable"),
    (KeitaroAuthError("Неверный ключ API Keitaro"), 502, "keitaro_auth_failed"),
    (KeitaroNotFoundError("Объект не найден в Keitaro"), 404, "keitaro_not_found"),
    (KeitaroRejectedError("Keitaro отклонил запрос: Alias is taken"), 422, "keitaro_rejected"),
])
def test_keitaro_errors_become_json_responses(make_settings, error, status, code):
    app = create_app(make_settings())

    @app.get("/api/test-keitaro-error")
    def raise_error():
        raise error

    response = TestClient(app).get("/api/test-keitaro-error")
    assert response.status_code == status
    assert response.json() == {"code": code, "message": error.message}
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_http_session.py tests/test_api_errors.py -v`
Expected: FAIL (`No module named 'app.keitaro'`).

- [ ] **Step 3: Реализовать `errors.py`, `http_session.py`, `app/api/errors.py`, подключить обработчик в `create_app`**

Ключ живёт только в заголовках внутреннего `httpx.Client`. Свои логи — `logging.getLogger("app.keitaro")`, уровень WARNING на повтор и на ошибку, в записи только метод, путь и статус (без URL целиком и без заголовков). Пауза между повторами — `time.sleep(retry_delay_seconds)`.

- [ ] **Step 4: Запустить — тесты проходят**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_http_session.py tests/test_api_errors.py -v`
Expected: все passed.

- [ ] **Step 5: Записать решения в `docs/decisions.md`** (раздел этапа 1):
- Мок HTTP — встроенный `httpx.MockTransport` вместо respx: лишняя зависимость не нужна, транспорт и так подменяется через конструктор.
- Отдельный фильтр логов для ключа не нужен: ключ есть только в заголовке внутреннего `httpx.Client`, ни наш код, ни httpx/httpcore заголовки не логируют. Это проверено тестом на уровне DEBUG.
- Политика повторов (см. Global Constraints) и разбор не-JSON ответов (HTML nginx → сообщение без текста Keitaro).

- [ ] **Step 6: Весь набор тестов и линтер**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`
Expected: всё зелёное.

- [ ] **Step 7: Commit**

```bash
git add backend/app/keitaro backend/app/api/errors.py backend/app/main.py backend/tests/test_keitaro_http_session.py backend/tests/test_api_errors.py docs/decisions.md
git commit -m "Клиент Keitaro: транспорт с таймаутами, повторами и понятными ошибками"
```

---

### Task 3: Модели Keitaro и типизированные методы клиента

**Files:**
- Create: `backend/app/keitaro/models.py`, `backend/app/keitaro/client.py`
- Modify: `backend/tests/conftest.py` (фикстура `keitaro_example`)
- Test: `backend/tests/test_keitaro_client.py`

**Interfaces:**
- Consumes: `KeitaroHttpSession` и ошибки (Task 2); примеры `docs/keitaro-examples/*.json` (Task 1) и выводы В1–В7 в `docs/decisions.md`.
- Produces:
  - `app.keitaro.models` — Pydantic-модели с `ConfigDict(extra="ignore", populate_by_name=True)`; числовые поля принимают строки-числа (lax-режим):
    - `KeitaroOffer(id: int, name: str, state: str)`
    - `KeitaroDomain(id: int, name: str, state: str)`
    - `KeitaroGroup(id: int, name: str, type: str)`
    - `KeitaroTrafficSource(id: int, name: str, state: str)`
    - `KeitaroCampaign(id: int, name: str, alias: str, type: str, state: str, domain: str | None = None, domain_id: int | None = None, group_id: int | None = None, traffic_source_id: int | None = None)`
    - `KeitaroStreamOffer(offer_id: int, share: int, state: str)`
    - `KeitaroStream(id: int, campaign_id: int, name: str, type: str, position: int, state: str, flow_schema: str = Field(alias="schema"), action_type: str | None = None, offers: list[KeitaroStreamOffer] = [])`
    - входные `@dataclass(frozen=True)`: `StreamOfferShare(offer_id: int, share: int)`, `NewCampaign(name: str, alias: str, domain_id: int, group_id: int, traffic_source_id: int)`, `NewCountryRedirectStream(campaign_id: int, name: str, position: int, country_code: str, redirect_url: str)`, `NewOffersStream(campaign_id: int, name: str, position: int, offers: tuple[StreamOfferShare, ...])`.
    
    Если реальный ответ расходится с этими типами (например, поле приходит `null`), прав реальный ответ: тип поправить и записать расхождение в `docs/decisions.md`.
  - `app.keitaro.client.KeitaroClient(Protocol)` и реализация `KeitaroHttpClient(session: KeitaroHttpSession)` с `from_settings(settings) -> KeitaroHttpClient`, `close()`, `__enter__`/`__exit__`. Методы:
    - чтение: `list_offers() -> list[KeitaroOffer]`, `list_domains() -> list[KeitaroDomain]`, `list_campaign_groups() -> list[KeitaroGroup]` (`GET /groups?type=campaigns`), `list_traffic_sources() -> list[KeitaroTrafficSource]`, `list_campaigns() -> list[KeitaroCampaign]`, `get_campaign(campaign_id: int) -> KeitaroCampaign`, `get_campaign_streams(campaign_id: int) -> list[KeitaroStream]`, `get_stream(stream_id: int) -> KeitaroStream`;
    - запись: `create_campaign(campaign: NewCampaign) -> KeitaroCampaign`, `create_country_redirect_stream(stream: NewCountryRedirectStream) -> KeitaroStream`, `create_offers_stream(stream: NewOffersStream) -> KeitaroStream`, `replace_stream_offers(stream_id: int, offers: Sequence[StreamOfferShare]) -> KeitaroStream`, `archive_stream(stream_id: int) -> None`, `archive_campaign(campaign_id: int) -> None`; служебный `close() -> None` тоже входит в Protocol (команда разведки закрывает клиент через интерфейс).
  - Тела запросов на запись — **ровно те, что Keitaro принял при разведке** (примеры 10, 12, 13, 16). Офферы в теле: `{"offer_id", "share", "state": "active"}`. `replace_stream_offers` шлёт только `{"offers": [...]}` (подтверждено В3/В4; если Task 1 остановилась на этом условии — Task 3 не начинать).
  - Если В2 показал отдельный ответ на занятый alias, `create_campaign` бросает `KeitaroAliasTakenError(KeitaroRejectedError)` (новый класс в `errors.py`), распознавая ответ по статусу и тексту из `11-create-campaign-alias-taken.json`. Если дубль был принят — класса нет, это уже записано в decisions.

- [ ] **Step 1: Фикстура примеров в `backend/tests/conftest.py`**

```python
EXAMPLES_DIR = REPOSITORY_ROOT / "docs" / "keitaro-examples"

@pytest.fixture
def keitaro_example():
    """Real Keitaro request/response pairs recorded by tools/keitaro_probe.py."""
    def load(name: str) -> dict:
        return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return load
```

- [ ] **Step 2: Написать падающие тесты** — `backend/tests/test_keitaro_client.py`

```python
def client_answering(status: int, body, sent: list[httpx.Request]) -> KeitaroHttpClient:
    """Replays a recorded Keitaro response and remembers what our client sent."""
    def handler(request):
        sent.append(request)
        return httpx.Response(status, json=body)
    session = KeitaroHttpSession("https://tracker.example.com", "test-key", timeout_seconds=5,
                                 max_retries=0, retry_delay_seconds=0,
                                 transport=httpx.MockTransport(handler))
    return KeitaroHttpClient(session)

def replay(example: dict, sent: list[httpx.Request]) -> KeitaroHttpClient:
    return client_answering(example["response"]["status"], example["response"]["body"], sent)

def test_list_offers_parses_real_example(keitaro_example):
    sent = []
    offers = replay(keitaro_example("01-get-offers"), sent).list_offers()
    assert [offer.id for offer in offers] == [18813]
    assert (sent[0].method, sent[0].url.path) == ("GET", "/admin_api/v1/offers")

def test_list_domains_parses_real_example(keitaro_example):
    domains = replay(keitaro_example("02-get-domains"), []).list_domains()
    assert [(domain.id, domain.name) for domain in domains] == [(1813, "kylovoa.com")]

def test_list_campaign_groups_asks_for_campaign_type(keitaro_example):
    sent = []
    groups = replay(keitaro_example("03-get-campaign-groups"), sent).list_campaign_groups()
    assert [(group.id, group.name) for group in groups] == [(10332, "FORTESTS")]
    assert sent[0].url.params["type"] == "campaigns"

def test_list_traffic_sources_parses_real_example(keitaro_example):
    sources = replay(keitaro_example("04-get-traffic-sources"), []).list_traffic_sources()
    assert [(source.id, source.name) for source in sources] == [(836, "FORTESTS")]

def test_create_campaign_sends_verified_body(keitaro_example):
    example = keitaro_example("10-create-campaign")
    body = example["request"]["body"]
    sent = []
    campaign = replay(example, sent).create_campaign(NewCampaign(
        name=body["name"], alias=body["alias"], domain_id=body["domain_id"],
        group_id=body["group_id"], traffic_source_id=body["traffic_source_id"]))
    assert (sent[0].method, sent[0].url.path) == ("POST", "/admin_api/v1/campaigns")
    assert json.loads(sent[0].content) == body
    assert (campaign.id, campaign.alias) == (example["response"]["body"]["id"], body["alias"])

def test_create_country_redirect_stream_sends_verified_body(keitaro_example):
    example = keitaro_example("12-create-stream-country-redirect")
    body = example["request"]["body"]
    sent = []
    stream = replay(example, sent).create_country_redirect_stream(NewCountryRedirectStream(
        campaign_id=body["campaign_id"], name="Flow 1", position=1, country_code="DE",
        redirect_url=body["action_payload"]))
    assert (sent[0].method, sent[0].url.path) == ("POST", "/admin_api/v1/streams")
    assert json.loads(sent[0].content) == body
    assert stream.id == example["response"]["body"]["id"]

def test_create_offers_stream_sends_verified_body(keitaro_example):
    example = keitaro_example("13-create-stream-offers")
    body = example["request"]["body"]
    sent = []
    stream = replay(example, sent).create_offers_stream(NewOffersStream(
        campaign_id=body["campaign_id"], name="Flow 2", position=2,
        offers=(StreamOfferShare(offer_id=18813, share=100),)))
    assert json.loads(sent[0].content) == body
    assert [(offer.offer_id, offer.share) for offer in stream.offers] == [(18813, 100)]

def test_get_campaign_streams_parses_real_example(keitaro_example):
    example = keitaro_example("15-get-campaign-streams")
    streams = replay(example, []).get_campaign_streams(campaign_id=1)
    by_name = {stream.name: stream for stream in streams}
    assert by_name["Flow 1"].flow_schema == "redirect" and by_name["Flow 1"].offers == []
    assert [(offer.offer_id, offer.share, offer.state) for offer in by_name["Flow 2"].offers] == [
        (18813, 100, "active")]

def test_get_stream_parses_real_example(keitaro_example):
    stream_before = keitaro_example("16-put-stream-offers-only")["observations"]["stream_before"]
    stream = client_answering(200, stream_before, []).get_stream(stream_before["id"])
    assert stream.name == "Probe"

def test_replace_stream_offers_sends_only_offers(keitaro_example):
    example = keitaro_example("16-put-stream-offers-only")
    sent = []
    stream_id = example["observations"]["stream_before"]["id"]
    replay(example, sent).replace_stream_offers(stream_id, [StreamOfferShare(18813, 100)])
    assert (sent[0].method, sent[0].url.path) == ("PUT", f"/admin_api/v1/streams/{stream_id}")
    assert json.loads(sent[0].content) == example["request"]["body"]

def test_replace_stream_offers_with_empty_list(keitaro_example):
    example = keitaro_example("18-put-stream-offers-empty")
    sent = []
    replay(example, sent).replace_stream_offers(1, [])
    assert json.loads(sent[0].content) == {"offers": []}

def test_archive_stream_and_campaign_use_delete(keitaro_example):
    sent = []
    replay(keitaro_example("21-delete-stream"), sent).archive_stream(21)
    replay(keitaro_example("22-delete-campaign"), sent).archive_campaign(10)
    assert [(request.method, request.url.path) for request in sent] == [
        ("DELETE", "/admin_api/v1/streams/21"), ("DELETE", "/admin_api/v1/campaigns/10")]

def test_models_accept_nulls_and_numeric_strings():
    campaign = KeitaroCampaign.model_validate({
        "id": "5", "name": "x", "alias": "a", "type": "position", "state": "active",
        "domain": None, "domain_id": None, "group_id": "10332", "traffic_source_id": None})
    assert (campaign.id, campaign.group_id, campaign.domain_id) == (5, 10332, None)
```

Плюс, если по В2 появился `KeitaroAliasTakenError`, — тест `test_alias_taken_raises_specific_error`: ответ из `11-create-campaign-alias-taken.json` → `pytest.raises(KeitaroAliasTakenError)`. Плюс `test_list_campaigns_parses_real_example` на `20-get-campaigns`: `campaign.domain` совпадает со значением из примера.

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_keitaro_client.py -v`
Expected: FAIL (`No module named 'app.keitaro.models'`).

- [ ] **Step 4: Реализовать `models.py` и `client.py`** по Interfaces. Сборка тел — приватные функции в `client.py` рядом с методами.

- [ ] **Step 5: Запустить — тесты проходят, затем весь набор и линтер**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`
Expected: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add backend/app/keitaro backend/tests/conftest.py backend/tests/test_keitaro_client.py docs/decisions.md
git commit -m "Клиент Keitaro: модели по реальным ответам и методы чтения и записи"
```

---

### Task 4: Команда разведки справочников

**Files:**
- Create: `backend/app/keitaro/references.py`, `backend/app/cli/__init__.py`, `backend/app/cli/recon.py`
- Test: `backend/tests/test_recon.py`

**Interfaces:**
- Consumes: `KeitaroClient`, `KeitaroHttpClient.from_settings`, модели (Task 3), `KeitaroError` (Task 2), `Settings`.
- Produces:
  - `app.keitaro.references.find_reference(items: Sequence[T], configured: str) -> T | None`, где `T` — любой объект с `id: int` и `name: str`. Значение обрезается от пробелов. Если оно из одних цифр — поиск по `id`, иначе точное совпадение `name`. Первое совпадение или `None`. Этап 2 переиспользует эту функцию для разрешения `CAMPAIGN_*`.
  - `app.cli.recon.render_recon(client: KeitaroClient, *, campaign_domain: str, campaign_group: str, campaign_traffic_source: str) -> str` — разделы «Домены», «Группы кампаний», «Источники трафика», «Офферы» (строки `id  name  state`; у групп — `id  name`). Затем раздел «Настройки создаватора» со строками `CAMPAIGN_DOMAIN=kylovoa.com → 1813`, `CAMPAIGN_GROUP=Missing → не найдено в Keitaro`, `CAMPAIGN_DOMAIN не задан`.
  - `app.cli.recon.main(*, load_settings: Callable[[], Settings] = Settings, build_client: Callable[[Settings], KeitaroClient] = KeitaroHttpClient.from_settings) -> int`. Коды выхода: 0 — успех; 1 — `KeitaroError` (в stderr `Ошибка Keitaro: {message}`); 2 — ошибка конфигурации (`pydantic.ValidationError`: в stderr имена отсутствующих переменных в верхнем регистре, без значений). Клиент закрывается в любом случае. Запуск: `python -m app.cli.recon` (`if __name__ == "__main__": sys.exit(main())`).

- [ ] **Step 1: Написать падающие тесты** — `backend/tests/test_recon.py`

```python
class FakeDictionaries:
    def list_domains(self): return [KeitaroDomain(id=1813, name="kylovoa.com", state="active")]
    def list_campaign_groups(self):
        return [KeitaroGroup(id=1, name="Other", type="campaigns"),
                KeitaroGroup(id=10332, name="FORTESTS", type="campaigns")]
    def list_traffic_sources(self): return [KeitaroTrafficSource(id=836, name="FORTESTS", state="active")]
    def list_offers(self): return [KeitaroOffer(id=18813, name="Test offer", state="active")]
    def close(self): pass

class FailingClient(FakeDictionaries):
    def list_domains(self): raise KeitaroAuthError("Неверный ключ API Keitaro", keitaro_status=401)

def test_find_reference_by_id_and_by_name():
    groups = FakeDictionaries().list_campaign_groups()
    assert find_reference(groups, "10332").id == 10332
    assert find_reference(groups, " FORTESTS ").id == 10332
    assert find_reference(groups, "fortests") is None
    assert find_reference(groups, "999") is None

def test_render_lists_dictionaries_and_resolves_configuration():
    text = render_recon(FakeDictionaries(), campaign_domain="kylovoa.com",
                        campaign_group="10332", campaign_traffic_source="FORTESTS")
    for section in ("Домены", "Группы кампаний", "Источники трафика", "Офферы"):
        assert section in text
    assert any("18813" in line and "Test offer" in line for line in text.splitlines())
    assert "CAMPAIGN_DOMAIN=kylovoa.com → 1813" in text
    assert "CAMPAIGN_GROUP=10332 → 10332" in text
    assert "CAMPAIGN_TRAFFIC_SOURCE=FORTESTS → 836" in text

def test_render_reports_unresolved_and_empty_configuration():
    text = render_recon(FakeDictionaries(), campaign_domain="", campaign_group="Missing",
                        campaign_traffic_source="FORTESTS")
    assert "CAMPAIGN_DOMAIN не задан" in text
    assert "CAMPAIGN_GROUP=Missing → не найдено в Keitaro" in text

def test_main_reports_keitaro_error_without_traceback(make_settings, capsys):
    code = main(load_settings=make_settings, build_client=lambda settings: FailingClient())
    captured = capsys.readouterr()
    assert code == 1
    assert "Ошибка Keitaro: Неверный ключ API Keitaro" in captured.err
    assert "Traceback" not in captured.err

def test_main_reports_missing_settings(monkeypatch, capsys):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    code = main(load_settings=lambda: Settings(_env_file=None),
                build_client=lambda settings: FakeDictionaries())
    captured = capsys.readouterr()
    assert code == 2
    assert "KEITARO_BASE_URL" in captured.err and "KEITARO_API_KEY" in captured.err

def test_output_never_contains_api_key(make_settings, capsys):
    code = main(load_settings=lambda: make_settings(campaign_domain="kylovoa.com"),
                build_client=lambda settings: FakeDictionaries())
    assert code == 0
    captured = capsys.readouterr()
    assert "test-secret-key-123" not in captured.out + captured.err
    assert "tracker.example.com" not in captured.out + captured.err
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_recon.py -v`
Expected: FAIL (`No module named 'app.keitaro.references'`).

- [ ] **Step 3: Реализовать `references.py` и `app/cli/recon.py`** по Interfaces. Код в `.py`, правило «циклы вместо цепочек» к Python не относится — пишем идиоматично.

- [ ] **Step 4: Запустить — тесты проходят, затем весь набор и линтер**

Run: `cd backend && .venv/Scripts/python -m pytest -v && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .`
Expected: всё зелёное.

- [ ] **Step 5: Запустить на реальном Keitaro и проверить, что секреты не светятся**

Run: `cd backend && out=$(mktemp) && .venv/Scripts/python -m app.cli.recon > "$out"; echo "exit $?"; cat "$out"`
(вывод сохраняется во временный файл вне репозитория)
Expected: `exit 0`; есть домен 1813 `kylovoa.com`, группа 10332 `FORTESTS`, источник 836 `FORTESTS`, оффер 18813; строки `CAMPAIGN_DOMAIN=kylovoa.com → 1813`, `CAMPAIGN_GROUP=FORTESTS → 10332`, `CAMPAIGN_TRAFFIC_SOURCE=FORTESTS → 836`.
Затем: команда из Task 1 Step 7, но по файлу `$out` → 0 вхождений ключа и адреса трекера.
Затем проверка с неверным ключом: `KEITARO_API_KEY=wrong .venv/Scripts/python -m app.cli.recon; echo "exit $?"` → `Ошибка Keitaro: Неверный ключ API Keitaro`, `exit 1`, без трейсбека.

- [ ] **Step 6: Commit**

```bash
git add backend/app/keitaro/references.py backend/app/cli backend/tests/test_recon.py
git commit -m "Команда разведки: домены, группы, источники и офферы Keitaro"
```

---

## Проверка готовности этапа

- [ ] `cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` — всё зелёное.
- [ ] `python -m app.cli.recon` работает на реальном Keitaro, в выводе нет ключа и адреса трекера (Task 4 Step 5).
- [ ] Во всех файлах из `git ls-files` нет ключа и адреса трекера: та же проверка-счётчик, что в Task 1 Step 7, по `git ls-files`.
- [ ] Все объекты, созданные разведкой, в архиве Keitaro (итог Task 1 Step 6); `clean_archive` не вызывался.
- [ ] `docs/decisions.md` содержит ответы В1–В7 и решения этапа; `docs/keitaro-examples/README.md` — оглавление.
- [ ] `git status` чистый; push — после подтверждения владельца.
- [ ] В итоговом сообщении этапа — ответы В1–В7 (особенно семантика PUT и поведение DELETE кампании) и решения этапа (MockTransport, отказ от фильтра логов, политика повторов).
