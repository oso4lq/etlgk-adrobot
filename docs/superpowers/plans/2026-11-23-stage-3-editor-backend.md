# Этап 3 — бэкенд редактора. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бэкенд редактора существующей кампании: локальная копия потоков и офферов в нашей БД, Fetch Streams, добавление, Remove, Bring back, Pin/Unpin, Cancel и Push to KT, выбор кампании из Keitaro. Готово, когда все сценарии из видео проходят в тестах с подменённым Keitaro и одна ручная проверка на тестовой кампании `test_oso4lq_editor_check` подтверждает, что Push меняет у потока только офферы.

**Architecture:** Слои по дизайну (6.1). Чистые функции в `app/domain/`: веса (`weights.py`), переходы состояний и черновик (`offer_bindings.py`), синхронизация с Keitaro (`offer_sync.py`). Сервисы в `app/services/`: `CampaignFetcher` (Fetch), `StreamEditor` (операции над черновиком), `StreamPublisher` (Push), `CampaignCatalog` (выбор кампании), `editor_views` (ответ API из строк БД). Модели и миграция `0003`, репозиторий `EditorRepository`, роутер `app/api/editor.py`. Keitaro трогают только Fetch (чтение) и Push (`replace_stream_offers` — тело `{"offers": [...]}`, проверено на этапе 1, В3–В6).

**Tech Stack:** Python ≥3.12 (локально 3.14), FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-18-adrobot-design.md` — разделы 5 (редактор), 6.1–6.3, 8 (п. 1–4, 7, сценарии из видео), 9 («Этап 3»); `docs/decisions.md` — разделы «разведка и дизайн» (веса, pin, Cancel, Push, Fetch), «этап 1» (В3–В7); `docs/video-transcript.md` — главный источник поведения; правила — `CLAUDE.md`, разделы 1, 6, 7, 8, 9.

## Global Constraints

- Не выдумывать API Keitaro. Этапу хватает методов `KeitaroClient`, которые уже есть: `get_campaign`, `get_campaign_streams`, `get_stream`, `list_campaigns`, `list_offers`, `replace_stream_offers`. Новых путей и полей Keitaro нет.
- Push шлёт в Keitaro только `{"offers": [...]}` через `replace_stream_offers`: список заменяется целиком (В4), `share` — целое, `0` и пустой список принимаются (В5, В6). Фильтры, действие, позиция и прочее не отправляются.
- Запись в реальный Keitaro — только в Task 12 и только в кампанию `test_oso4lq_editor_check`, созданную нашей API в этом же Task. `clean_archive` не вызывать никогда.
- Защита общего Keitaro: Push разрешён только кампаниям, чьё **текущее** имя в Keitaro начинается с `KEITARO_WRITE_NAME_PREFIX` (пусто — без ограничений). Fetch и просмотр — для любой кампании (пишут только в нашу БД).
- Секреты — ключ API и адрес трекера: их нет в логах, ответах API, сообщениях об ошибках, `docs/keitaro-examples/` и коммитах. Логгеры `httpx`/`httpcore` остаются на WARNING.
- Веса — целые, сумма активных после пересчёта ровно 100, остаток по +1 первым незакреплённым по `sort_order`. Пересчёт запускают только добавление, Remove и Bring back; Pin, Unpin, Fetch и Cancel веса не пересчитывают.
- Pin — локальная настройка: поток от неё не желтеет, Cancel её не откатывает, Remove снимает.
- Ответ любой ошибки нашей API — `{"code": str, "message": str}` с осмысленным HTTP-статусом; ошибка Keitaro не превращается в 500 и не меняет нашу БД.
- Схема БД — только миграциями Alembic (`0003`), накат и откат работают, `test_migrations_match_models` зелёный.
- Синхронный стек. Бизнес-логика — в `domain` и `services`; роутеры только принимают запрос и отдают готовую схему.
- Имена без сокращений, комментарии объясняют «почему». Коммиты — по-русски, по делу, последняя строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Работа идёт в ветке `worktree-stage-3-editor-backend` (worktree `.claude/worktrees/stage-3-editor-backend`), ветка пушится в `origin`; в `main` — только после подтверждения владельца.
- Команды — Git Bash на Windows, из `backend/` worktree: `.venv/Scripts/python ...` (своя `.venv` worktree, см. Task 1); путь содержит пробел — в кавычках.

## Review Focus

1. **Ответ на PUT потерян, а Keitaro его применил** (таймаут после записи). Повторный Push не должен застрять на 409 «сначала Fetch»: если в Keitaro уже ровно наш черновик, публикация засчитывается без второго PUT. Тест: Task 9 `test_push_after_lost_response_reconciles_without_second_put`.
2. **Один и тот же оффер дважды в потоке Keitaro** (через API это возможно, а у нас уникальность `(stream_id, keitaro_offer_id)`). Fetch не падает на ограничении БД, а объединяет строки. Тесты: Task 3 `test_merge_remote_offers`, Task 7 `test_fetch_merges_duplicate_offer`.
3. **Закреплённые веса из Keitaro в сумме больше 100** (Fetch берёт веса как есть), затем Bring back. Отрицательных весов нет: незакреплённые получают 0, поток показывает проблему, Push запрещён. Тесты: Task 1 (строка `[(A,True,60),(A,True,60),(A,False,5)]`), Task 2 `test_notices_pinned_over_100`.
4. **Поток удалён (заархивирован) в Keitaro, а у нас по нему черновик.** Push отвечает 409 «поток удалён в Keitaro», а не 404 или 500. Fetch убирает поток с отдельным предупреждением о потерянных изменениях. Тесты: Task 9 `test_push_conflict_when_stream_archived_or_missing`, Task 7 `test_fetch_deletes_streams_missing_in_keitaro`.
5. **Кампанию переименовали в Keitaro после Fetch, и префикса в имени больше нет.** Push проверяет живое имя, а не сохранённое при Fetch, и отказывает с 403. Тест: Task 9 `test_push_refused_when_campaign_lost_prefix_after_fetch`.

## Решения этапа (на согласование; в Task 12 переносятся в `docs/decisions.md`, раздел «этап 3»)

Неоднозначности, которые спецификация не закрывает. Для каждой выбран вариант с наименьшим сюрпризом:

1. **`has_offers` не хранится, а вычисляется:** у потока есть хотя бы одна привязка. Поток с офферами в Keitaro после Fetch всегда получает привязки; поток, у которого все офферы ушли в архив, остаётся потоком с офферами (с ним работают Bring back и добавление). Отличие от 5.1 спецификации — на один столбец меньше и не нужно поддерживать его согласованность.
2. **В адресах нашей API — id из Keitaro** (кампании, потока, оффера), а не наши внутренние id: они стабильны и видны пользователю в админке.
3. **Оффер `disabled` в Keitaro** у нас считается удалённым (так в спецификации). Push отправляет только активные офферы, поэтому после Push выключенный оффер исчезает из потока в Keitaro, а у нас остаётся в архиве потока, и его можно вернуть через Bring back. Слать `state: disabled` не проверяли, поэтому не шлём.
4. **Дубли оффера в одном потоке Keitaro** объединяются в одну привязку: она активна, если активна хоть одна строка, вес — сумма долей активных строк, порядок — по первому появлению.
5. **Закреплённые из Keitaro в сумме больше 100:** остаток считается как `max(0, 100 − сумма закреплённых)`, незакреплённые получают 0. Текст проблемы — «открепите оффер».
6. **Проблема «сумма не 100» бывает двух видов.** Все активные закреплены или закреплённых больше 100: «Сумма весов N%, нужно 100% — открепите оффер». Веса пришли из Keitaro как есть: «Сумма весов N%, нужно 100% — веса пересчитаются при добавлении, удалении или возврате оффера».
7. **Fetch переводит оффер, которого нет в Keitaro, в «удалён» и снимает закрепление** — как Remove в обёртке («как будто удалили руками», видео 04:46).
8. **Fetch и черновики.** У потока-черновика без `force` обновляются только имя и позиция, офферы не трогаются. Поток, которого больше нет в Keitaro, удаляется локально даже с черновиком: опубликовать черновик всё равно некуда. Об этом выдаётся отдельное предупреждение с именами потоков, чьи изменения потеряны.
9. **Push.** Сначала локальные проверки (черновик, сумма весов, префикс по сохранённому имени), затем чтение из Keitaro. Если кампания в Keitaro не прошла проверку префикса — 403. Поток удалён или не найден — 409. Активные офферы в Keitaro уже совпадают с черновиком — публикация засчитывается без PUT (п. 1 Review Focus). Совпадают с опубликованной версией — PUT. Иначе — 409. Порядок офферов при сравнении не учитывается.
10. **Состояние и повторные нажатия.** Remove удалённого и Bring back активного — 409 `offer_state_conflict`. Pin и Unpin идемпотентны. Cancel потока без черновика ничего не меняет и отвечает 200. Push потока без черновика — 409 `stream_not_draft`.
11. **Remove оффера, добавленного без публикации,** работает как Remove любого другого: оффер серый, поток жёлтый. Cancel удаляет привязку совсем. После Push оффер остаётся в архиве потока. Особого случая не вводим.
12. **Имена офферов** берутся из каталога офферов (кэш `GET /offers`). Если оффер не виден тестовому пользователю — «Оффер {id}», а сохранённое имя не затирается.
13. **Выбор кампании:** поиск такой же, как у офферов (префикс id или подстрока имени, точный id первым, не больше 20), новые кампании (бо́льший id) сверху, список кэшируется на 30 секунд (константа, а не переменная окружения).
14. **Не делаем на этом этапе:** CORS-заголовки у ответа 500 (фронтенд ходит через прокси `/api`, запрос не кросс-доменный), авторизацию и блокировки (не-цели дизайна).

## Коды ошибок редактора

| Код | HTTP | Текст | Где |
|---|---|---|---|
| `offer_state_conflict` | 409 | «Оффер {id} уже удалён из потока» / «Оффер {id} уже активен в потоке» / «Удалённый оффер {id} нельзя закрепить» | Task 2 |
| `pinned_sum_exceeds_100` | 422 | «Нельзя закрепить оффер {id}: сумма закреплённых весов станет {N}%, больше 100%» | Task 2 |
| `campaign_not_fetched` | 404 | «Кампания {id} ещё не загружена в редактор — выполните Fetch Streams» | Task 7 |
| `stream_not_found` | 404 | «Поток {id} не найден в редакторе — выполните Fetch Streams» | Task 8 |
| `offer_not_in_stream` | 404 | «Оффера {offer_id} нет в потоке {stream_id}» | Task 8 |
| `stream_without_offers` | 422 | «Поток {id} без офферов: добавлять офферы можно только в потоки, где они уже есть» | Task 8 |
| `offer_already_in_stream` | 409 | «Оффер {id} уже есть в потоке» | Task 8 |
| `offer_not_found` | 422 | «Оффер {id} не найден в Keitaro» (класс создаватора, переносится в `offer_catalog`) | Task 6 |
| `stream_not_draft` | 409 | «Нечего публиковать: в потоке нет неопубликованных изменений» | Task 9 |
| `weights_sum_not_100` | 422 | текст проблемы из п. 6 решений | Task 9 |
| `write_forbidden` | 403 | «Публикация запрещена: название кампании не начинается с «{prefix}»» | Task 9 |
| `keitaro_stream_changed` | 409 | «Офферы потока в Keitaro изменились после последнего Fetch Streams — выполните Fetch Streams» / «Поток удалён в Keitaro — выполните Fetch Streams» | Task 9 |

Ошибки Keitaro (`keitaro_unavailable`, `keitaro_not_found`, `keitaro_rejected`, …) пробрасываются как есть — их уже маппит общий обработчик `AppError`.

---

## Структура файлов

```
backend/
  app/domain/weights.py            — OfferStatus, WeightSlot, recalculate_weights, pinned_total, active_total
  app/domain/notices.py            — Notice (код + текст предупреждения или проблемы)
  app/domain/offer_bindings.py     — OfferBinding (Protocol), переходы состояний, черновик, StreamNotices
  app/domain/offer_sync.py         — RemoteOffer, merge_remote_offers, sync_bindings, remote_state
  app/domain/search.py             — search_by_id_or_name (общий для офферов и кампаний)
  app/domain/write_guard.py        — is_write_allowed, write_forbidden_message
  app/db/models.py                 — + EditorCampaign, EditorStream, StreamOffer
  app/repositories/editor.py       — EditorRepository
  app/services/ttl_cache.py        — TtlCache (кэш списка с TTL, вынесен из OfferCatalog)
  app/services/offer_catalog.py    — на TtlCache и search_by_id_or_name; + names(); + OfferNotFoundError
  app/services/campaign_catalog.py — CampaignCatalog (выбор кампании)
  app/services/editor_errors.py    — ошибки редактора (таблица выше)
  app/services/campaign_fetcher.py — CampaignFetcher, FetchResult (Fetch Streams)
  app/services/stream_editor.py    — StreamEditor (add, remove, bring back, pin, unpin, cancel)
  app/services/stream_publisher.py — StreamPublisher (Push to KT)
  app/services/editor_views.py     — строки БД → схемы ответа (is_draft, can_push, проблемы)
  app/services/campaign_creator.py — импорт OfferNotFoundError и is_write_allowed
  app/schemas/editor.py            — схемы API редактора
  app/api/editor.py                — эндпоинты редактора и выбора кампании
  app/api/dependencies.py, app/main.py — сервисы редактора в app.state
  migrations/versions/0003_editor.py
  tools/compare_campaigns.py       — compare_values (публичная, с nested_ignored)
  tools/stream_snapshot.py         — снимок потока до Push и сравнение после (только чтение)
  tests/fakes.py                   — копии вместо ссылок, помощники для потоков и офферов
  tests/test_weights.py, test_offer_bindings.py, test_offer_sync.py, test_editor_repository.py,
  tests/test_campaign_catalog.py, test_campaign_fetcher.py, test_stream_editor.py,
  tests/test_stream_publisher.py, test_api_editor.py, test_editor_video_scenarios.py,
  tests/test_stream_snapshot.py    — новые
  tests/test_migrations.py, test_fakes.py, test_offer_catalog.py, test_campaign_creator.py — правки
docs/decisions.md                  — раздел «этап 3»
docs/keitaro-examples/26-editor-push-check.json, README.md
```

---

### Task 1: Чистая функция весов

**Files:**
- Create: `backend/app/domain/weights.py`
- Test: `backend/tests/test_weights.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `class OfferStatus(StrEnum)`: `ACTIVE = "active"`, `REMOVED = "removed"`
  - `FULL_WEIGHT = 100`
  - `@dataclass(frozen=True) class WeightSlot: status: OfferStatus; is_pinned: bool; weight: int`
  - `recalculate_weights(slots: Sequence[WeightSlot]) -> list[int]` — новые веса в порядке входа (вход уже в `sort_order`)
  - `pinned_total(slots: Sequence[WeightSlot]) -> int` — сумма весов закреплённых **активных**
  - `active_total(slots: Sequence[WeightSlot]) -> int` — сумма весов активных

- [ ] **Step 1: Окружение worktree**

В основной `.venv` пакет установлен editable и указывает на `app` основной копии, поэтому у worktree своё окружение:
Run: `cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]" && .venv/Scripts/python -m pytest -q`
Expected: `200 passed`.

- [ ] **Step 2: Написать тесты**

```python
A, R = OfferStatus.ACTIVE, OfferStatus.REMOVED

def slots(*items): return [WeightSlot(status, pinned, weight) for status, pinned, weight in items]

@pytest.mark.parametrize(("items", "expected"), [
    # video 02:06: a fourth offer is added, nothing pinned
    ([(A, False, 34), (A, False, 33), (A, False, 33), (A, False, 0)], [25, 25, 25, 25]),
    ([(A, False, 0)] * 3, [34, 33, 33]),
    ([(A, False, 0)] * 7, [15, 15, 14, 14, 14, 14, 14]),
    # video 05:24: pinned 25 stays, the two others share the rest
    ([(A, True, 25), (A, False, 25), (A, False, 0)], [25, 38, 37]),
    ([(A, False, 0), (A, True, 25), (A, False, 0)], [38, 25, 37]),
    ([(A, False, 50), (R, False, 30), (A, False, 20)], [50, 0, 50]),
    ([(R, True, 30), (A, False, 0), (A, False, 0)], [0, 50, 50]),      # a removed pin does not count
    ([(A, True, 40), (A, True, 50)], [40, 50]),                        # all pinned: unchanged
    ([(A, True, 100), (A, False, 10), (A, False, 0)], [100, 0, 0]),
    ([(A, True, 60), (A, True, 60), (A, False, 5)], [60, 60, 0]),      # pins from Keitaro over 100
    ([(R, False, 10), (R, False, 0)], [0, 0]),
    ([], []),
])
def test_recalculate_weights(items, expected):
    assert recalculate_weights(slots(*items)) == expected

def test_unpinned_offers_always_complete_100():
    for pinned in range(0, 101, 7):
        for unpinned_count in range(1, 12):
            items = [(A, True, pinned)] + [(A, False, 0)] * unpinned_count
            assert sum(recalculate_weights(slots(*items))) == 100

def test_totals_count_only_active():
    items = slots((A, True, 30), (R, True, 20), (A, False, 50))
    assert (pinned_total(items), active_total(items)) == (30, 80)
```

- [ ] **Step 3: Запустить — падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_weights.py -q`
Expected: FAIL (`ModuleNotFoundError: app.domain.weights`).

- [ ] **Step 4: Реализовать `app/domain/weights.py`**

Удалённые → 0. Закреплённые активные сохраняют вес. `remainder = max(0, FULL_WEIGHT − pinned_total)`, `n` незакреплённых активных получают `remainder // n`, первые `remainder % n` из них по порядку — ещё +1. При `n = 0` веса активных не меняются. `max(0, …)` нужен потому, что Fetch берёт закреплённые веса из Keitaro как есть и их сумма может превысить 100. Комментарий в модуле — ссылка на 5.2 спецификации и «Округление весов» в `docs/decisions.md`.

- [ ] **Step 5: Запустить — проходят**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_weights.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/weights.py backend/tests/test_weights.py
git commit -m "Редактор: чистая функция пересчёта весов"
```

---

### Task 2: Привязки офферов — переходы состояний и черновик

**Files:**
- Create: `backend/app/domain/notices.py`, `backend/app/domain/offer_bindings.py`
- Test: `backend/tests/test_offer_bindings.py`

**Interfaces:**
- Consumes: Task 1 — `OfferStatus`, `WeightSlot`, `recalculate_weights`, `pinned_total`, `active_total`, `FULL_WEIGHT`.
- Produces:
  - `notices.py`: `@dataclass(frozen=True) class Notice: code: str; message: str`
  - `class OfferBinding(Protocol)` — изменяемые атрибуты `keitaro_offer_id: int`, `sort_order: int`, `status: str`, `weight: int`, `is_pinned: bool`, `published_status: str | None`, `published_weight: int | None`. Ему соответствует ORM `StreamOffer` (Task 4); в тестах — простой `@dataclass`.
  - Все функции принимают привязки одного потока в любом порядке и работают в порядке `sort_order`:
    - `is_draft(bindings) -> bool` — есть привязка, где `(status, weight) != (published_status, published_weight)`
    - `recalculate(bindings) -> None` — присваивает результат `recalculate_weights`
    - `remove(bindings, binding) -> None` — `removed`, вес 0, закрепление снято, пересчёт; уже `removed` → `OfferStateConflictError`
    - `bring_back(bindings, binding) -> None` — `active`, пересчёт; уже `active` → `OfferStateConflictError`
    - `pin(bindings, binding) -> None` — `removed` → `OfferStateConflictError`; уже закреплён → ничего; `pinned_total + binding.weight > 100` → `PinLimitExceededError`; веса не меняются
    - `unpin(binding) -> None`
    - `cancel_draft(bindings) -> list[OfferBinding]` — у опубликованных `status, weight := published_*`; возвращает неопубликованные (`published_status is None`), их вызывающий удаляет; закрепления не трогаются
    - `mark_published(bindings) -> None` — `published_* := status, weight` у всех
    - `published_shares(bindings) -> dict[int, int]` — `{offer_id: published_weight}` для `published_status == active`
    - `working_shares(bindings) -> dict[int, int]` — `{offer_id: weight}` для `status == active`
    - `active_in_order(bindings) -> list[OfferBinding]`
    - `next_sort_order(bindings) -> int` — `max + 1`, для пустого списка 0
    - `@dataclass(frozen=True) class StreamNotices: problems: list[Notice]; warnings: list[Notice]`
    - `stream_notices(bindings) -> StreamNotices`
  - Ошибки (`AppError`): `OfferStateConflictError(message)` — `offer_state_conflict`, 409; `PinLimitExceededError(offer_id, total)` — `pinned_sum_exceeds_100`, 422 (тексты — таблица кодов).
  - Тексты уведомлений (`stream_notices`):
    - проблема `weights_sum_not_100` — есть активные и `active_total != 100`; если незакреплённых активных нет или `pinned_total > 100`: `f"Сумма весов {total}%, нужно 100% — открепите оффер"`, иначе `f"Сумма весов {total}%, нужно 100% — веса пересчитаются при добавлении, удалении или возврате оффера"`;
    - предупреждение `unpinned_offers_get_zero` — есть незакреплённые активные и `pinned_total == 100`: `"Закреплённые офферы занимают 100%: незакреплённые получают 0%"`;
    - предупреждение `no_active_offers` — привязки есть, активных нет: `"В потоке нет активных офферов: после публикации поток в Keitaro останется без офферов"`;
    - пустой список привязок — ни проблем, ни предупреждений.

- [ ] **Step 1: Написать тесты**

Помощник в тесте: `@dataclass class Binding` с полями протокола; `published(offer_id, weight, order)` — опубликованная активная привязка (`published_* == status, weight`); `added(offer_id, order)` — неопубликованная (`published_status=None, published_weight=None`, вес 0).

```python
def test_clean_stream_is_not_draft():
    assert not is_draft([published(1, 50, 0), published(2, 50, 1)])

def test_unpublished_or_changed_binding_makes_draft():
    assert is_draft([published(1, 100, 0), added(2, 1)])
    changed = published(1, 100, 0); changed.weight = 60
    assert is_draft([changed])

def test_remove_greys_out_unpins_and_recalculates():
    bindings = [published(1, 34, 0), published(2, 33, 1), published(3, 33, 2)]
    bindings[1].is_pinned = True
    remove(bindings, bindings[1])
    assert [(b.status, b.weight, b.is_pinned) for b in bindings] == [
        ("active", 50, False), ("removed", 0, False), ("active", 50, False)]
    assert is_draft(bindings)

def test_remove_twice_is_conflict():  # message "Оффер 2 уже удалён из потока"
def test_bring_back_keeps_pinned_weight():
    # video 05:24: pinned 25, one active, one removed → 25 / 38 / 37
def test_bring_back_active_is_conflict():  # "Оффер 1 уже активен в потоке"
def test_pin_and_unpin_change_neither_weights_nor_draft_state():
def test_pin_over_100_is_rejected():
    # pinned 60 + pin 50 → PinLimitExceededError, message contains "станет 110%"
def test_pin_removed_is_conflict():
def test_pin_twice_is_noop():
def test_cancel_draft_restores_published_and_returns_unpublished():
    # [published 1 removed by remove(), added 2, pinned published 3] →
    # 1 active with its published weight, returned == [binding 2], 3 still pinned, not draft without 2
def test_mark_published_copies_working_version_including_removed():
    # removed → published_status "removed", published_weight 0; is_draft False
def test_published_and_working_shares():
def test_notices_clean_100():               # problems == warnings == []
def test_notices_all_pinned_not_100():      # problem weights_sum_not_100, "Сумма весов 90%, нужно 100% — открепите оффер"
def test_notices_fetched_sum_not_100():     # unpinned 25 + 25 → "…50%… — веса пересчитаются при добавлении, удалении или возврате оффера"
def test_notices_pinned_over_100():         # pinned 60 + 60 + unpinned 0 → "…120%… — открепите оффер"
def test_notices_pinned_take_everything():  # pinned 100 + unpinned 0 → warning unpinned_offers_get_zero, no problem
def test_notices_no_active_offers():        # all removed → warning no_active_offers, no problem
```

- [ ] **Step 2: Запустить — падают**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_offer_bindings.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать `notices.py` и `offer_bindings.py`** по интерфейсу выше. `recalculate` строит `WeightSlot` из привязок, отсортированных по `sort_order`, и раскладывает результат обратно. Сравнение статусов — через `OfferStatus` (строки в БД равны значениям enum).

- [ ] **Step 4: Запустить — проходят**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_offer_bindings.py tests/test_weights.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/notices.py backend/app/domain/offer_bindings.py backend/tests/test_offer_bindings.py
git commit -m "Редактор: переходы состояний привязок, черновик и предупреждения потока"
```

---

### Task 3: Синхронизация с Keitaro — чистая функция

**Files:**
- Create: `backend/app/domain/offer_sync.py`
- Test: `backend/tests/test_offer_sync.py`

**Interfaces:**
- Consumes: Task 1 `OfferStatus`; Task 2 `OfferBinding`.
- Produces:
  - `@dataclass(frozen=True) class RemoteOffer: offer_id: int; share: int; is_active: bool`
  - `merge_remote_offers(offers: Iterable[RemoteOffer]) -> list[RemoteOffer]` — один элемент на `offer_id` в порядке первого появления; активен, если активна хоть одна строка; `share` — сумма долей активных строк (0, если активных нет)
  - `remote_state(offer: RemoteOffer) -> tuple[OfferStatus, int]` — `(ACTIVE, share)` или `(REMOVED, 0)`
  - `sync_bindings(bindings: Sequence[OfferBinding], remote: Sequence[RemoteOffer]) -> list[RemoteOffer]` — известные привязки получают `status, weight = published_status, published_weight = remote_state(...)`; привязки, которых нет в `remote`, получают `removed, 0` в обеих версиях; у ставших `removed` закрепление снимается; закрепления активных сохраняются. Возвращает офферы из `remote`, которых у нас нет, в порядке Keitaro (`remote` уже объединён `merge_remote_offers`).

- [ ] **Step 1: Написать тесты**

```python
def test_known_active_offer_takes_keitaro_share():          # binding 1 (50) + remote (1, 70, True) → active 70, published active 70
def test_offer_missing_in_keitaro_becomes_removed_and_stream_stays_clean():
    # video 04:30: binding pinned 25 not in remote → removed, 0, published removed/0, is_pinned False, is_draft False
def test_disabled_offer_becomes_removed():                  # remote (1, 40, False) → removed, 0
def test_removed_offer_back_in_keitaro_is_active():          # removed binding + remote (1, 30, True) → active 30
def test_pins_survive_and_take_keitaro_weight():             # pinned binding 25 + remote (1, 40, True) → pinned, 40
def test_unknown_offers_returned_in_keitaro_order():          # remote 3, 1, 2 with binding 1 → [3, 2]

@pytest.mark.parametrize(("offers", "expected"), [
    ([(1, 30, True), (2, 70, True), (1, 20, True)], [(1, 50, True), (2, 70, True)]),
    ([(3, 40, False), (3, 60, True)], [(3, 60, True)]),
    ([(4, 10, False), (4, 20, False)], [(4, 0, False)]),
])
def test_merge_remote_offers(offers, expected):
    merged = merge_remote_offers(RemoteOffer(*item) for item in offers)
    assert [(o.offer_id, o.share, o.is_active) for o in merged] == expected
```

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_offer_sync.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать `app/domain/offer_sync.py`** по интерфейсу.

- [ ] **Step 4: Запустить — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_offer_sync.py -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/offer_sync.py backend/tests/test_offer_sync.py
git commit -m "Редактор: синхронизация привязок с офферами потока Keitaro"
```

---

### Task 4: Таблицы редактора, миграция 0003, репозиторий

**Files:**
- Modify: `backend/app/db/models.py`, `backend/tests/test_migrations.py` (ревизия головы `"0002"` → `"0003"` в трёх местах + новый тест)
- Create: `backend/migrations/versions/0003_editor.py`, `backend/app/repositories/editor.py`
- Test: `backend/tests/test_editor_repository.py`

**Interfaces:**
- Consumes: `Base`, `UtcDateTime` из `app/db`.
- Produces:
  - `EditorCampaign` (`editor_campaigns`): `id`, `keitaro_campaign_id: int` (unique), `name: str` (`Text`), `last_fetched_at: datetime` (`UtcDateTime`), `streams: list[EditorStream]` (relationship, `order_by=EditorStream.position`, `cascade="all, delete-orphan"`, `back_populates="campaign"`)
  - `EditorStream` (`editor_streams`): `id`, `campaign_id` (FK `editor_campaigns.id`, `ondelete="CASCADE"`), `keitaro_stream_id: int` (unique), `name: str` (`Text`), `position: int`, `campaign`, `offers: list[StreamOffer]` (`order_by=StreamOffer.sort_order`, `cascade="all, delete-orphan"`)
  - `StreamOffer` (`stream_offers`): `id`, `stream_id` (FK `editor_streams.id`, `ondelete="CASCADE"`), `keitaro_offer_id: int`, `offer_name: str` (`Text`), `sort_order: int`, `status: str` (`String(16)`), `weight: int`, `is_pinned: bool` (default `False`), `published_status: str | None` (`String(16)`), `published_weight: int | None`; `UniqueConstraint("stream_id", "keitaro_offer_id")`
  - Имена из Keitaro — `Text`: длина чужих имён неизвестна, а на Postgres `String(255)` упал бы.
  - `EditorRepository(session)`: `find_campaign(keitaro_campaign_id: int) -> EditorCampaign | None`; `add_campaign(keitaro_campaign_id: int, name: str, fetched_at: datetime) -> EditorCampaign` (только `session.add`); `find_stream(keitaro_stream_id: int) -> EditorStream | None`; `commit() -> None` (при ошибке `rollback` и проброс, как в `CreatedCampaignsRepository`).

- [ ] **Step 1: Написать тесты**

```python
def test_campaign_streams_and_offers_round_trip_in_order(db_session):
    # streams added with positions 2, 1; offers with sort_order 1, 0 → after commit and expire_all:
    # [s.position for s in campaign.streams] == [1, 2]; offers ordered by sort_order
def test_removing_stream_deletes_its_offers(db_session):
    # campaign.streams.remove(stream); commit → select(StreamOffer) is empty
def test_same_offer_twice_in_stream_is_rejected(db_session):
    # two StreamOffer(keitaro_offer_id=18813) in one stream → commit raises IntegrityError
def test_failed_commit_rolls_back_session(db_session):
    # after the IntegrityError the repository session is usable: find_campaign works
```

В `test_migrations.py`: голова — `"0003"`; новый `test_editor_tables_follow_migrations` — после `upgrade head` есть три таблицы с колонками из интерфейса, после `downgrade 0002` их нет, а `created_campaigns` осталась.

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_editor_repository.py tests/test_migrations.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать модели, миграцию `0003` (`down_revision = "0002"`, `downgrade` удаляет таблицы в обратном порядке) и репозиторий.** Имена ограничений берутся из `NAMING_CONVENTION` (`op.f(...)`), как в `0002`.

- [ ] **Step 4: Запустить — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS (включая `test_migrations_match_models`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/migrations/versions/0003_editor.py backend/app/repositories/editor.py backend/tests/test_editor_repository.py backend/tests/test_migrations.py
git commit -m "Редактор: таблицы кампаний, потоков и привязок, миграция 0003, репозиторий"
```

---

### Task 5: Фейк Keitaro для редактора

**Files:**
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_fakes.py`

**Interfaces:**
- Consumes: модели `app/keitaro/models.py`.
- Produces (для Task 7–12):
  - Все методы чтения и создания возвращают глубокие копии (`model_copy(deep=True)`). Состояние меняется только методами фейка или прямой записью теста в `fake.campaigns` / `fake.streams`. Так изменение ответа сервисом не может незаметно поменять «Keitaro» (замечание ревью этапа 2).
  - Помощники подготовки — **не** пишутся в `fake.calls`:
    - `add_offer(offer_id: int, name: str) -> None` — в `fake.offers`
    - `add_campaign(name: str) -> KeitaroCampaign` — активная кампания, `alias=f"fake{id}"`
    - `add_stream(campaign_id: int, name: str, position: int, offers: Sequence[tuple[int, int] | tuple[int, int, str]] = ()) -> KeitaroStream` — `(offer_id, share[, state])`, состояние по умолчанию `"active"`; `schema` — `"landings"`, если офферы есть, иначе `"redirect"`
    - `set_stream_offers(stream_id: int, offers: Sequence[tuple[int, int] | tuple[int, int, str]]) -> None` — правка руками в админке

- [ ] **Step 1: Написать тесты**

```python
def test_returned_objects_are_copies():
    fake = FakeKeitaroClient()
    campaign = fake.add_campaign("test_oso4lq_x")
    stream = fake.add_stream(campaign.id, "Flow 2", 2, [(18813, 100)])
    fake.get_stream(stream.id).offers.clear()
    fake.get_campaign_streams(campaign.id)[0].name = "changed"
    fake.list_campaigns()[0].name = "changed"
    assert fake.streams[stream.id].offers[0].offer_id == 18813
    assert fake.streams[stream.id].name == "Flow 2"
    assert fake.campaigns[campaign.id].name == "test_oso4lq_x"

def test_arrangement_helpers_are_not_recorded_and_support_disabled_offers():
    # add_campaign/add_stream/set_stream_offers/add_offer → fake.calls == []
    # set_stream_offers(id, [(1, 60), (2, 40, "disabled")]) → states ["active", "disabled"]
```

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_fakes.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать.** Id кампаний и потоков из помощников берутся из тех же счётчиков, что и у `create_*`.

- [ ] **Step 4: Запустить весь набор — существующие тесты не задеты.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fakes.py backend/tests/test_fakes.py
git commit -m "Фейк Keitaro: копии вместо ссылок, помощники для потоков и офферов"
```

---

### Task 6: Каталоги — имена офферов и выбор кампании

**Files:**
- Create: `backend/app/domain/search.py`, `backend/app/services/ttl_cache.py`, `backend/app/services/campaign_catalog.py`
- Modify: `backend/app/services/offer_catalog.py`, `backend/app/services/campaign_creator.py` (импорт `OfferNotFoundError`), `backend/tests/test_campaign_creator.py` (импорт)
- Test: `backend/tests/test_offer_catalog.py` (+1 тест), `backend/tests/test_campaign_catalog.py`

**Interfaces:**
- Consumes: `KeitaroClient.list_offers`, `KeitaroClient.list_campaigns`; Task 5 `add_campaign`.
- Produces:
  - `search.py`: `class NamedItem(Protocol): id: int; name: str`; `SEARCH_LIMIT = 20`; `search_by_id_or_name[T: NamedItem](items: Sequence[T], query: str, limit: int = SEARCH_LIMIT) -> list[T]` — правила «Поиск офферов» из `docs/decisions.md` (префикс id или подстрока названия без учёта регистра, точный id первым, пустой запрос — первые `limit`). Тело переносится из `OfferCatalog.search` без изменений.
  - `TtlCache[T](load: Callable[[], list[T]], ttl_seconds: float, clock: Callable[[], float] = time.monotonic)`: `get() -> tuple[list[T], bool]` (элементы и признак «только что загружены»); `reload() -> list[T]`; блокировка внутри. Если `load` упал, старый кэш и метка времени не меняются.
  - `OfferCatalog` — тот же публичный интерфейс поверх `TtlCache` и `search_by_id_or_name`, плюс `names() -> dict[int, str]` (из кэша, без принудительной перезагрузки при промахе). `OfferNotFoundError` переезжает в `app/services/offer_catalog.py` (код и текст прежние).
  - `CAMPAIGN_LIST_TTL_SECONDS = 30`; `CampaignCatalog(client, ttl_seconds: float = CAMPAIGN_LIST_TTL_SECONDS, clock=time.monotonic)`, `search(query: str) -> list[KeitaroCampaign]` — кампании по убыванию id, затем `search_by_id_or_name`.

- [ ] **Step 1: Написать тесты**

```python
# test_offer_catalog.py
def test_names_come_from_cache_without_forced_reload(fake, catalog):
    catalog.names(); catalog.names()
    assert fake.calls.count(("list_offers",)) == 1
    assert catalog.names()[18813] == "Test offer 18813"

# test_campaign_catalog.py
def test_search_lists_newest_first_and_matches_id_or_name(fake):
    # campaigns "test_oso4lq_a" (id 1), "other" (id 2), "test_oso4lq_b" (id 3)
    # search("") → ids [3, 2, 1]; search("oso4lq") → [3, 1]; search("2") → [2]
def test_campaign_list_is_cached_for_ttl(fake):   # clock 0 → 1 call; clock 29 → 1; clock 31 → 2
```

Существующие тесты `test_offer_catalog.py` и `test_campaign_creator.py` проходят без изменений логики.

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_offer_catalog.py tests/test_campaign_catalog.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать.** В `OfferCatalog.find` проверка и перезагрузка при промахе больше не атомарны. Худший случай — лишний `GET /offers` при одновременных запросах; комментарий объясняет, почему это приемлемо.

- [ ] **Step 4: Запустить весь набор.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/search.py backend/app/services/ttl_cache.py backend/app/services/campaign_catalog.py backend/app/services/offer_catalog.py backend/app/services/campaign_creator.py backend/tests/test_offer_catalog.py backend/tests/test_campaign_catalog.py backend/tests/test_campaign_creator.py
git commit -m "Каталоги: общий поиск и кэш, имена офферов, выбор кампании для редактора"
```

---

### Task 7: Fetch Streams

**Files:**
- Create: `backend/app/services/editor_errors.py` (только `CampaignNotFetchedError`; остальные добавляют Task 8 и 9), `backend/app/services/campaign_fetcher.py`
- Modify: `backend/tests/conftest.py` (фикстуры `editor_repository` = `EditorRepository(db_session)`, `offer_catalog` = `OfferCatalog(fake, ttl_seconds=300)`; их используют и Task 8–9, 11)
- Test: `backend/tests/test_campaign_fetcher.py`

**Interfaces:**
- Consumes: Task 2 `is_draft`, `cancel_draft`, `Notice`; Task 3 `RemoteOffer`, `merge_remote_offers`, `sync_bindings`, `remote_state`; Task 4 модели и `EditorRepository`; Task 6 `OfferCatalog.names()`; `KeitaroClient.get_campaign`, `get_campaign_streams`; Task 5 помощники фейка.
- Produces:
  - `@dataclass(frozen=True) class FetchResult: campaign: EditorCampaign; kept_draft_stream_ids: list[int]; notices: list[Notice]`
  - `CampaignFetcher(client: KeitaroClient, offer_catalog: OfferCatalog, clock: Callable[[], datetime] = lambda: datetime.now(UTC))`
    - `fetch(repository: EditorRepository, keitaro_campaign_id: int, *, force: bool = False) -> FetchResult`
    - `load(repository: EditorRepository, keitaro_campaign_id: int) -> EditorCampaign` — нет в БД → `CampaignNotFetchedError(keitaro_campaign_id)` (404)
  - `OFFER_NAME_FALLBACK = "Оффер {offer_id}"`
  - Уведомления `FetchResult.notices`:
    - `draft_streams_kept`: `f"Не обновлены потоки с неопубликованными изменениями: {names}. Опубликуйте или отмените изменения либо повторите Fetch Streams с отбросом черновиков"`
    - `streams_deleted_in_keitaro`: `f"Потоков больше нет в Keitaro, они убраны из редактора: {names}"`
    - `drafts_lost_with_deleted_streams`: `f"Неопубликованные изменения потеряны вместе с удалёнными в Keitaro потоками: {names}"`
    - `names` — имена в кавычках-ёлочках через запятую: `«Flow 2», «Flow 3»`.

Порядок `fetch` (все чтения Keitaro — до первой записи в БД, один `commit` в конце):
1. `get_campaign` (404 Keitaro пробрасывается, БД не тронута), `get_campaign_streams`, `offer_catalog.names()`.
2. Найти или создать `EditorCampaign`, обновить `name` и `last_fetched_at`.
3. Для каждого потока Keitaro по `position`: `remote = merge_remote_offers(RemoteOffer(o.offer_id, o.share, o.state == "active") for o in stream.offers)`.
   - Нового потока у нас нет → создать `EditorStream` и привязки из `remote` (опубликованные, `sort_order` по порядку Keitaro).
   - Поток есть, черновик и `force=False` → обновить только `name` и `position`, id — в `kept_draft_stream_ids`.
   - Иначе: при черновике (`force=True`) — `cancel_draft` и удалить возвращённые привязки; затем `sync_bindings`, новые офферы добавить в конец (`next_sort_order`), обновить `name`, `position` и имена офферов из каталога (если в каталоге имени нет — сохранённое не трогать).
4. Наши потоки, которых нет в ответе Keitaro, удалить (`campaign.streams.remove`), собрать уведомления.

- [ ] **Step 1: Написать тесты.** Фикстура сценария: кампания `test_oso4lq_editor`, поток «Flow 1» (позиция 1, без офферов), «Flow 2» (позиция 2, офферы 1001/34, 1002/33, 1003/33); офферы 1001–1005 добавлены в каталог фейка с именами `Offer 1001` и т. д.

```python
def test_fetch_creates_streams_in_position_order():
    # streams [(position, name, len(offers))] == [(1, "Flow 1", 0), (2, "Flow 2", 3)]
    # Flow 2 offers: names "Offer 1001".., weights [34, 33, 33], all active, published == working
def test_fetch_takes_weights_from_keitaro_as_is():               # Keitaro 25/25 → 25/25, not draft
def test_fetch_offer_deleted_in_keitaro_turns_removed_and_stream_stays_clean():
def test_fetch_disabled_offer_is_removed():
def test_fetch_new_offer_in_keitaro_is_appended_as_active():
def test_fetch_keeps_pins_and_takes_pinned_weight_from_keitaro():
def test_fetch_keeps_draft_stream_and_reports_it():
    # draft (added 1004 locally) + Keitaro changed shares and renamed the stream →
    # offers untouched (1004 still unpublished), stream name updated,
    # kept_draft_stream_ids == [flow2_id], notice code "draft_streams_kept"
def test_fetch_force_discards_draft_and_syncs():
def test_fetch_deletes_streams_missing_in_keitaro():
    # archive Flow 2 in fake (state "deleted") after a local draft →
    # stream gone with its offers, notices "streams_deleted_in_keitaro" and "drafts_lost_with_deleted_streams"
def test_fetch_merges_duplicate_offer():                       # Keitaro [(1001, 30), (1001, 20), (1002, 50)] → 1001: 50
def test_fetch_offer_unknown_to_catalog_gets_fallback_name():   # 77777 → "Оффер 77777"
def test_fetch_unknown_campaign_writes_nothing():               # KeitaroNotFoundError, no EditorCampaign rows
def test_fetch_keitaro_failure_leaves_db_unchanged():
    # second fetch with fake.fail("get_campaign_streams", KeitaroUnavailableError(...)) → raises; rows as after the first fetch
def test_load_unfetched_campaign_is_not_found():                # CampaignNotFetchedError, code "campaign_not_fetched"
```

Проверки состояния БД — после `db_session.expire_all()`: убеждаемся, что изменения закоммичены, а не просто висят в сессии.

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_campaign_fetcher.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать `CampaignFetcher`** по порядку выше. Ни одной записи в Keitaro: в тестах `fake.calls` содержит только `get_campaign`, `get_campaign_streams`, `list_offers`.

- [ ] **Step 4: Запустить — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/editor_errors.py backend/app/services/campaign_fetcher.py backend/tests/conftest.py backend/tests/test_campaign_fetcher.py
git commit -m "Редактор: Fetch Streams — синхронизация потоков и офферов, черновики не затираются"
```

---

### Task 8: Операции над черновиком потока

**Files:**
- Create: `backend/app/services/stream_editor.py`
- Modify: `backend/app/services/editor_errors.py` (+ `StreamNotFoundError`, `OfferNotInStreamError`, `StreamWithoutOffersError`, `OfferAlreadyInStreamError`)
- Test: `backend/tests/test_stream_editor.py`

**Interfaces:**
- Consumes: Task 2 (`remove`, `bring_back`, `pin`, `unpin`, `recalculate`, `cancel_draft`, `next_sort_order`); Task 4 (`EditorRepository.find_stream`, `commit`, `StreamOffer`); Task 6 (`OfferCatalog.find`, `OfferNotFoundError`); Task 7 (`CampaignFetcher` — для подготовки в тестах).
- Produces: `StreamEditor(offer_catalog: OfferCatalog)`. Все методы принимают `(repository: EditorRepository, keitaro_stream_id: int, ...)`, коммитят и возвращают `EditorStream`:
  - `add_offer(repository, keitaro_stream_id, offer_id: int)`. Привязок у потока нет → `StreamWithoutOffersError`. Оффер активен в потоке → `OfferAlreadyInStreamError`. Оффер в архиве потока → `bring_back`. Иначе `offer_catalog.find(offer_id)` (нет → `OfferNotFoundError`), новая `StreamOffer(status="active", weight=0, published_status=None, published_weight=None, sort_order=next_sort_order(...), offer_name=offer.name)`, затем `recalculate`.
  - `remove_offer`, `bring_back_offer`, `pin_offer`, `unpin_offer` `(repository, keitaro_stream_id, offer_id: int)` — привязки нет → `OfferNotInStreamError`.
  - `cancel(repository, keitaro_stream_id)` — `cancel_draft`, возвращённые привязки удаляются из `stream.offers`.
  - Поток не найден → `StreamNotFoundError`.
  - В Keitaro не обращается: `fake.calls` после операций не содержит ничего, кроме `list_offers`.

- [ ] **Step 1: Написать тесты.** Подготовка — Fetch сценария Task 7 (Flow 2: 1001/34, 1002/33, 1003/33).

```python
def test_add_offer_gives_25_each_and_makes_stream_draft_without_touching_keitaro():
    # weights [25, 25, 25, 25]; new binding published_status None, offer_name "Offer 1004"; is_draft
    # no replace_stream_offers in fake.calls; fake stream still has 3 offers
def test_add_active_offer_is_conflict():
def test_add_archived_offer_works_as_bring_back():           # no new row, status active, recalculated
def test_add_unknown_offer_is_rejected():                    # OfferNotFoundError, no new row
def test_add_to_stream_without_offers_is_rejected():         # Flow 1 → StreamWithoutOffersError
def test_unknown_stream_is_not_found():
def test_remove_greys_out_and_recalculates():                # 1002 → removed 0; [50, 0, 50]; draft
def test_bring_back_keeps_pinned_weight():
    # as in the video: Keitaro 1001–1004 at 25 → fetch → set_stream_offers([(1001, 25), (1002, 25)]) → fetch
    # → pin 1001 → bring back 1003 → [(1001, 25, pinned), (1002, 38), (1003, 37), (1004, removed, 0)]
def test_pin_and_unpin_keep_weights_and_stream_clean():
def test_pin_over_100_is_rejected():                         # Keitaro 1001/60, 1002/60 → pin 1001 → pin 1002 → PinLimitExceededError
def test_cancel_restores_published_and_drops_unpublished():
    # add 1004, remove 1002 → cancel → offers [1001 34, 1002 33, 1003 33], 1004 binding gone, offer still in catalog, not draft, pins kept
def test_cancel_clean_stream_changes_nothing():
def test_operation_on_offer_not_in_stream_is_not_found():
def test_changes_are_committed():                            # after expire_all the state is the same
```

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stream_editor.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать.** Новая привязка добавляется через `stream.offers.append(...)` до `recalculate`, чтобы пересчёт её видел.

- [ ] **Step 4: Запустить — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/stream_editor.py backend/app/services/editor_errors.py backend/tests/test_stream_editor.py
git commit -m "Редактор: добавление, Remove, Bring back, Pin и Cancel над черновиком потока"
```

---

### Task 9: Push to KT

**Files:**
- Create: `backend/app/domain/write_guard.py`, `backend/app/services/stream_publisher.py`
- Modify: `backend/app/services/editor_errors.py` (+ `StreamNotDraftError`, `WeightsNotReadyError`, `WriteForbiddenError`, `KeitaroStreamChangedError`), `backend/app/services/campaign_creator.py` (проверка префикса через `is_write_allowed`)
- Test: `backend/tests/test_stream_publisher.py`

**Interfaces:**
- Consumes: Task 2 (`is_draft`, `stream_notices`, `mark_published`, `published_shares`, `working_shares`, `active_in_order`); Task 3 (`RemoteOffer`, `merge_remote_offers`); Task 4; `KeitaroClient.get_campaign`, `get_stream`, `replace_stream_offers`, `StreamOfferShare`.
- Produces:
  - `write_guard.py`: `is_write_allowed(campaign_name: str, prefix: str) -> bool` (пустой префикс — да); `write_forbidden_message(prefix: str) -> str`
  - `StreamPublisher(client: KeitaroClient, settings: Settings)`, `push(repository: EditorRepository, keitaro_stream_id: int) -> EditorStream`

Порядок `push`:
1. Поток из БД (`StreamNotFoundError`). Не черновик → `StreamNotDraftError`. Есть проблемы `stream_notices` → `WeightsNotReadyError(problems[0].message)`. Сохранённое имя кампании без префикса → `WriteForbiddenError`. Всё это — без обращений к Keitaro.
2. `get_campaign(campaign.keitaro_campaign_id)`: живое имя без префикса → `WriteForbiddenError`; сохранённое имя обновляется живым.
3. `get_stream(keitaro_stream_id)`: `KeitaroNotFoundError`, `state != "active"` или чужой `campaign_id` → `KeitaroStreamChangedError` («Поток удалён в Keitaro — …»). Архивный поток всё ещё отвечает на GET (В7).
4. `remote = {o.offer_id: o.share for o in merge_remote_offers(...) if o.is_active}`. `remote == working_shares` → `mark_published`, `commit`, без PUT. `remote != published_shares` → `KeitaroStreamChangedError` («Офферы потока в Keitaro изменились …»).
5. `replace_stream_offers(id, [StreamOfferShare(b.keitaro_offer_id, b.weight) for b in active_in_order(...)])`, затем `mark_published`, `commit`. Ошибка Keitaro пробрасывается, БД не меняется.

- [ ] **Step 1: Написать тесты.** Подготовка — Fetch сценария Task 7; `StreamPublisher(fake, make_settings(keitaro_write_name_prefix="test_oso4lq_"))`.

```python
def test_push_sends_active_offers_in_order_and_publishes():
    # add 1004 → push → last call == ("replace_stream_offers", flow2_id,
    #   (StreamOfferShare(1001, 25), StreamOfferShare(1002, 25), StreamOfferShare(1003, 25), StreamOfferShare(1004, 25)))
    # not draft; fake stream offers == the four with 25
def test_push_writes_nothing_but_offers():
    # write calls in fake.calls == ["replace_stream_offers"] (no create_*, archive_*)
def test_push_removed_offer_disappears_from_keitaro_and_stays_archived():
    # remove 1002 → push → Keitaro [1001 50, 1003 50]; our 1002 removed, published removed/0
def test_push_stream_without_active_offers_sends_empty_list():
def test_push_clean_stream_is_rejected():                      # StreamNotDraftError, fake.calls empty
def test_push_with_weights_not_100_is_rejected():              # WeightsNotReadyError, no Keitaro calls
def test_push_refused_for_campaign_without_prefix():           # campaign "other_x" → WriteForbiddenError, no Keitaro calls
def test_push_refused_when_campaign_lost_prefix_after_fetch():
    # fetch, add 1004, fake.campaigns[id].name = "renamed" → WriteForbiddenError, no replace call
def test_push_without_prefix_setting_is_allowed():
def test_push_conflict_when_keitaro_offers_changed():
    # set_stream_offers(flow2, [(1001, 100)]) after fetch → KeitaroStreamChangedError, still draft, no replace call
def test_push_conflict_when_stream_archived_or_missing():
    # state "deleted" → conflict; del fake.streams[id] → conflict (not KeitaroNotFoundError)
def test_push_keitaro_error_leaves_draft():
    # fake.fail("replace_stream_offers", KeitaroRejectedError("…", 422)) → raises KeitaroRejectedError; still draft, published unchanged
def test_push_after_lost_response_reconciles_without_second_put():
    # fake.fail("replace_stream_offers", KeitaroUnavailableError("…"), after_applying=True) → raises;
    # second push → no new replace call, stream clean
def test_push_keeps_pins():
```

В `test_campaign_creator.py` поведение префикса не меняется: существующие тесты должны пройти.

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stream_publisher.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать** по порядку выше. В комментариях: почему имя кампании читается заново (защита общего Keitaro по текущему имени) и почему совпадение с черновиком засчитывается как публикация (потерянный ответ PUT).

- [ ] **Step 4: Запустить — проходят.** Run: `cd backend && .venv/Scripts/python -m pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/write_guard.py backend/app/services/stream_publisher.py backend/app/services/editor_errors.py backend/app/services/campaign_creator.py backend/tests/test_stream_publisher.py
git commit -m "Редактор: Push to KT — меняются только офферы потока, сверка с Keitaro перед записью"
```

---

### Task 10: API редактора и выбора кампании

**Files:**
- Create: `backend/app/schemas/editor.py`, `backend/app/services/editor_views.py`, `backend/app/api/editor.py`
- Modify: `backend/app/api/dependencies.py`, `backend/app/main.py`
- Test: `backend/tests/test_api_editor.py`

**Interfaces:**
- Consumes: Task 2 (`is_draft`, `stream_notices`), Task 6 (`CampaignCatalog`), Task 7 (`CampaignFetcher`, `FetchResult`), Task 8 (`StreamEditor`), Task 9 (`StreamPublisher`, `is_write_allowed`, `write_forbidden_message`).
- Produces:
  - Схемы (`app/schemas/editor.py`):
    - `NoticeResponse { code: str, message: str }`
    - `OfferBindingResponse { offer_id: int, name: str, status: Literal["active", "removed"], weight: int, is_pinned: bool, is_published: bool }` (`is_published` — `published_status is not None`)
    - `StreamResponse { keitaro_stream_id: int, name: str, position: int, has_offers: bool, is_draft: bool, can_push: bool, can_cancel: bool, offers: list[OfferBindingResponse], problems: list[NoticeResponse], warnings: list[NoticeResponse] }`
    - `CampaignResponse { keitaro_campaign_id: int, name: str, write_allowed: bool, last_fetched_at: datetime, streams: list[StreamResponse] }`
    - `FetchResponse { campaign: CampaignResponse, kept_draft_stream_ids: list[int], notices: list[NoticeResponse] }`
    - `AddOfferRequest { offer_id: int }`, `KeitaroCampaignResponse { id: int, name: str }`
  - `editor_views.py`: `stream_response(stream: EditorStream, write_prefix: str) -> StreamResponse`, `campaign_response(campaign: EditorCampaign, write_prefix: str) -> CampaignResponse`, `fetch_response(result: FetchResult, write_prefix: str) -> FetchResponse`. Правила: `has_offers = bool(stream.offers)`; поток без офферов — пустые `offers`, `problems` и `warnings`, флаги `False`; у черновика без права записи в `problems` добавляется `write_forbidden` с текстом `write_forbidden_message`; `can_push = is_draft and not problems`; `can_cancel = is_draft`; офферы в `sort_order`.
  - Эндпоинты (все отдают схемы выше):
    - `GET /api/keitaro-campaigns?query=` → `list[KeitaroCampaignResponse]`
    - `POST /api/editor/campaigns/{keitaro_campaign_id}/fetch?force=false` → `FetchResponse`
    - `GET /api/editor/campaigns/{keitaro_campaign_id}` → `CampaignResponse`
    - `POST /api/editor/streams/{keitaro_stream_id}/offers` (тело `AddOfferRequest`) → `StreamResponse`
    - `POST /api/editor/streams/{keitaro_stream_id}/offers/{offer_id}/remove | bring-back | pin | unpin` → `StreamResponse`
    - `POST /api/editor/streams/{keitaro_stream_id}/push` → `StreamResponse`
    - `POST /api/editor/streams/{keitaro_stream_id}/cancel` → `StreamResponse`
  - `app.state`: `campaign_catalog`, `campaign_fetcher`, `stream_editor`, `stream_publisher`; зависимости `get_campaign_catalog`, `get_campaign_fetcher`, `get_stream_editor`, `get_stream_publisher`, `get_write_prefix`.

- [ ] **Step 1: Написать тесты** (`TestClient`, фейк и временная SQLite — как `make_api` в `test_api_creator.py`; кампания `test_oso4lq_editor` из Task 7)

```python
def test_campaign_picker_searches_by_name_and_id(api):
def test_fetch_returns_plain_and_offers_streams(api):
    # streams[0] == {"keitaro_stream_id": .., "name": "Flow 1", "position": 1, "has_offers": False,
    #                "is_draft": False, "can_push": False, "can_cancel": False, "offers": [], "problems": [], "warnings": []}
    # streams[1].offers weights [34, 33, 33], names "Offer 1001".., all is_published
def test_get_campaign_before_fetch_is_404(api):          # {"code": "campaign_not_fetched", "message": "Кампания … ещё не загружена …"}
def test_add_offer_returns_draft_with_weights_summing_to_100(api):   # sum == 100, is_draft, can_push, can_cancel
def test_remove_bring_back_pin_unpin_endpoints(api):
def test_push_and_cancel_endpoints(api, fake):            # push → is_draft False, fake stream has 4 offers; cancel on clean → 200
def test_fetch_force_query_parameter(api):
def test_draft_in_campaign_without_prefix_cannot_be_pushed(api, fake):
    # campaign "other_campaign": fetch ok, add ok, write_allowed False, can_push False,
    # problems contain code "write_forbidden"; push → 403 {"code": "write_forbidden", ...}
def test_editor_errors_have_code_and_message(api):
    # add to Flow 1 → 422 stream_without_offers;
    # Keitaro Flow 2 at 1001/60, 1002/60 → pin 1001, pin 1002 → 422 pinned_sum_exceeds_100;
    # unknown stream → 404 stream_not_found; missing offer_id → 422 invalid_request
def test_keitaro_conflict_on_push_is_409(api, fake):     # keitaro_stream_changed
```

- [ ] **Step 2: Запустить — падают.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_api_editor.py -q` — Expected: FAIL.

- [ ] **Step 3: Реализовать** схемы, представления, роутер и подключение в `create_app`. Роутер не содержит логики: открыть сессию → вызвать сервис → `stream_response(...)`.

- [ ] **Step 4: Запустить весь набор и линтер.** Run: `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` — Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/editor.py backend/app/services/editor_views.py backend/app/api/editor.py backend/app/api/dependencies.py backend/app/main.py backend/tests/test_api_editor.py
git commit -m "API редактора: выбор кампании, Fetch, операции над офферами, Push и Cancel"
```

---

### Task 11: Сценарии из видео — сквозные тесты

**Files:**
- Test: `backend/tests/test_editor_video_scenarios.py`

**Interfaces:**
- Consumes: Task 7–10 (`CampaignFetcher`, `StreamEditor`, `StreamPublisher`, `stream_response`), Task 5 (помощники фейка).
- Produces: —

Исходное состояние «как в ролике» (00:07–00:33): кампания `test_oso4lq_video`, «Flow 1» (страна AU → google.com, без офферов), «Flow 2» с офферами 1001/1002/1003 (34/33/33); в каталоге офферы 1001–1005. Утверждения — через `stream_response`, то есть ровно то, что увидит экран: `is_draft` («жёлтый»), `status` («серый»), веса. Каждый тест — один шаг ролика; общий помощник воспроизводит предыдущие шаги.

- [ ] **Step 1: Написать тесты**

```python
def test_step_1_fetch_streams_shows_offers_and_plain_stream():          # 00:33–01:27
def test_step_2_added_offer_gives_25_each_and_yellow_but_keitaro_has_three():   # 01:27–02:25
def test_step_3_push_sends_four_offers_and_stream_turns_white():       # 02:25–02:37
def test_step_4_cancel_drops_unpublished_offer_and_stream_turns_white():   # 02:37–03:12, offer 1005 still in catalog
def test_step_5_removed_offer_is_grey_zero_and_after_push_gone_from_keitaro_but_archived():  # 03:13–03:54
def test_step_6_bring_back_and_push_returns_offer_to_keitaro():        # 03:54–04:05
def test_step_7_offers_deleted_in_keitaro_turn_grey_after_fetch():     # 04:06–04:58, stream white, Bring back possible
def test_step_8_pinned_weight_survives_bring_back_and_push():          # 04:59–05:57: Keitaro gets 25 / 38 / 37
```

- [ ] **Step 2: Запустить.** Run: `cd backend && .venv/Scripts/python -m pytest tests/test_editor_video_scenarios.py -q` — Expected: PASS. Если шаг падает, ищется расхождение с транскрипцией; поведение не подгоняется под тест.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_editor_video_scenarios.py
git commit -m "Редактор: сценарии из видео — по тесту на шаг"
```

---

### Task 12: Снимок потока, проверка на реальном Keitaro, журнал решений

**Files:**
- Modify: `backend/tools/compare_campaigns.py` (`_compare` → публичная `compare_values(reference, candidate, path, ignored, nested_ignored=NESTED_IGNORED_FIELDS)`)
- Create: `backend/tools/stream_snapshot.py`, `backend/tests/test_stream_snapshot.py`, `docs/keitaro-examples/26-editor-push-check.json`
- Modify: `docs/keitaro-examples/README.md` (строка 26), `docs/decisions.md` (раздел «этап 3»)

**Interfaces:**
- Consumes: `KeitaroHttpSession` (сырой JSON — модели отбрасывают нужные поля), `sanitize`, `write_example` из `tools/keitaro_examples.py`, `compare_values`.
- Produces:
  - `stream_settings_differences(before: dict, after: dict) -> list[str]` — без ключа `offers`; `action_payload` `None` и `""` считаются равными (В3); все прочие поля и вложенные id (фильтры) сравниваются.
  - `python -m tools.stream_snapshot save STREAM_ID PATH` — сырой `GET /streams/{id}` в файл вне репозитория.
  - `python -m tools.stream_snapshot diff STREAM_ID PATH [--record NAME]` — код выхода 0 — расхождений нет, 1 — есть расхождения или ошибка Keitaro, 2 — ошибка конфигурации. `--record` пишет пример с очисткой секретов, как `compare_campaigns --record`. Keitaro только читается.

- [ ] **Step 1: Тесты инструмента** (по образцу `test_compare_campaigns.py`, сессия подменяется через `build_session`)

```python
def test_offers_and_empty_action_payload_are_not_differences():
    # before action_payload None, after "" and other offers → []
def test_changed_filter_is_a_difference():
    # filter payload ["DE"] → ["FR"] → ["stream.filters[0].payload[0]: эталон 'DE', проверяемая 'FR'"]
def test_save_then_diff_round_trip(tmp_path):   # exit code 0 without changes; 1 after a change in the fake session
```
Run: `cd backend && .venv/Scripts/python -m pytest tests/test_stream_snapshot.py tests/test_compare_campaigns.py -q` — сначала FAIL, после реализации PASS.

- [ ] **Step 2: Commit инструмента**

```bash
git add backend/tools/compare_campaigns.py backend/tools/stream_snapshot.py backend/tests/test_stream_snapshot.py
git commit -m "Инструмент приёмки: снимок потока до Push и сравнение после"
```

- [ ] **Step 3: Подготовка к реальному Keitaro.** В корень worktree скопировать `.env` основной копии (`git check-ignore .env` должен его показать), затем `cd backend && .venv/Scripts/python -m alembic upgrade head` и запустить бэкенд в фоне: `.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000`.

- [ ] **Step 4: Сценарий на тестовой кампании** (оффер 18813; запросы — `curl` к `http://localhost:8000`; после каждого шага сверять ответ нашей API и `GET /streams/{id}` в Keitaro)
  1. `POST /api/campaigns` `{"name": "test_oso4lq_editor_check", "country": "DE", "offer_id": 18813}` → id кампании `C`, потоки `S1`, `S2`.
  2. `POST /api/editor/campaigns/C/fetch` → `S1` без офферов, `S2` с 18813/100, оба не черновики.
  3. `python -m tools.stream_snapshot save S2 "$CLAUDE_JOB_DIR/tmp/s2-before.json"` (снимок вне репозитория).
  4. Remove 18813 → `S2` черновик, 0%, предупреждение `no_active_offers` → Push → в Keitaro у `S2` `offers: []`, у нас 18813 серый, поток белый.
  5. `stream_snapshot diff S2 …/s2-before.json` → «Расхождений нет» (проверка после первого Push, раздел 9 `CLAUDE.md`).
  6. Bring back → 100% → Push → в Keitaro 18813/100.
  7. В админке Keitaro (Playwright, только кампания `C`) убрать оффер из Flow 2 и сохранить → Fetch → 18813 серый, поток белый.
  8. `stream_snapshot diff S2 …/s2-before.json --record 26-editor-push-check` → «Расхождений нет».
  9. Push при изменениях в Keitaro: Bring back (у нас черновик 18813/100) → в админке вернуть 18813 в Flow 2 с долей 50 и сохранить → Push → 409 `keitaro_stream_changed`, Keitaro не изменился → Fetch с `force=true` → у нас 18813/50, поток белый. Если админка не даёт долю, отличную от 100, при единственном оффере — шаг пропускается, и это записывается в журнал решений (конфликт покрыт тестами Task 9).
  10. `python -m tools.archive_test_campaign C --confirm` → кампания и потоки в архиве. Остановить бэкенд, удалить скопированный `.env` и локальную БД worktree.

- [ ] **Step 5: Документы.** `docs/decisions.md` — раздел «2026-11-23 — этап 3 (редактор, бэкенд)»: решения 1–14 из шапки плана (что выбрано и почему), таблица кодов ошибок, результат шага 4 (id кампании, что проверено, кампания в архиве, `clean_archive` не вызывался). `docs/keitaro-examples/README.md` — строка `26-editor-push-check.json`. Проверка секретов: в `git ls-files` нет ключа и адреса трекера (как на этапах 1–2).

- [ ] **Step 6: Commit**

```bash
git add docs/decisions.md docs/keitaro-examples/26-editor-push-check.json docs/keitaro-examples/README.md
git commit -m "Приёмка редактора на реальном Keitaro: Push меняет только офферы, решения этапа 3"
```

---

## Проверка готовности этапа

- [ ] `cd backend && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check .` — всё зелёное.
- [ ] Все сценарии 6.3 `CLAUDE.md` покрыты тестами: Fetch (Task 7), добавление (Task 8), Push (Task 9), Cancel (Task 8), Remove (Task 8–9), Bring back (Task 8–9), Pin (Task 2, 8), удаление в Keitaro (Task 3, 7); видео — Task 11.
- [ ] `alembic downgrade 0002` и `upgrade head` работают (`test_migrations.py`).
- [ ] Ручная проверка Task 12 пройдена, пример 26 записан, тестовая кампания в архиве, `clean_archive` не вызывался.
- [ ] Ключа и адреса трекера нет ни в одном файле из `git ls-files`.
- [ ] `docs/decisions.md` — раздел «этап 3» полный.
- [ ] Ветка `worktree-stage-3-editor-backend` запушена; `git status` чистый; в `main` — после подтверждения владельца.
- [ ] Итоговое сообщение этапа: решения 1–14, коды ошибок, результат проверки на реальном Keitaro, что кампания в архиве.
