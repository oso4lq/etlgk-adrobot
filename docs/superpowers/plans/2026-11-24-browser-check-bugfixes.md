# Исправление багов из проверки в браузере: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Исправить шесть багов из `docs/bugs.md`, найденных при проверке в браузере 24.11.2026.

**Architecture:** Точечные правки без новых слоёв. Баг 1 — доменное правило в `backend/app/domain/offer_bindings.py`. Баг 6 — понятная ошибка в `CampaignFetcher` и правило показа в `editor-view.ts`. Баги 2–5 — фронтенд: store создаватора, общий автокомплит, разметка и CSS.

**Tech Stack:** FastAPI, pytest, ruff; Angular 22 (signals, signal forms, новый control flow), vitest + jsdom.

**Spec:** `docs/bugs.md` (список багов) + решение владельца по багу 1 (ниже). Правила проекта — `CLAUDE.md`, журнал решений — `docs/decisions.md`.

## Global Constraints

- Ветка `fix-browser-check-bugs`, от `main`. История не переписывается, force-push запрещён.
- Каждый баг — отдельный коммит с тестом, который без исправления падает (TDD). Коммиты по-русски, в конце строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Решение владельца по багу 1: **Unpin пересчитывает веса, только если сумма весов активных офферов потока ≠ 100.** При сумме 100 Unpin, как и раньше, весов не меняет.
- Изменённые правила записываются в `docs/decisions.md` (правится существующий раздел, а не дописывается противоречащий новый).
- Шаблоны: только `@if/@for/@switch`, никаких вызовов методов и геттеров в привязках отображения — всё готовится в view-функциях или `computed`. Обработчики событий (`(click)="…"`) допустимы, как и сейчас.
- TypeScript: `for...of` вместо цепочек `.filter().map()`; методы `Object.*` — только для обхода всего подряд.
- Тексты для пользователя — по-русски, без ASCII-замен букв.
- Команды проверки:
  - бэкенд (из `backend/`): `.venv/Scripts/python -m pytest -q` и `.venv/Scripts/ruff check .`
  - фронтенд (из `frontend/`): `pnpm test --watch=false`, `pnpm lint`, `pnpm build`
- Реальный Keitaro и эмулятор в задачах 1–5 не трогаются; живая проверка — только в задаче 6.

## Review Focus

1. **Закреплённый и одновременно неопубликованный оффер** — в ячейке флагов выводится «закреплённе опубликован» по той же причине, что в баге 3. Ожидается «закреплён не опубликован». Тест — в задаче 5.
2. **Unpin при сумме > 100 после Fetch** (закреплены 60 и 50): открепили 50 → 60/40, сумма 100. Если закреплённых всё ещё больше 100, подсказка «открепите оффер» остаётся верной. Тест — в задаче 1.
3. **Поиск упал с ошибкой** — под полем должно быть только «Поиск недоступен: …», без «Ничего не найдено» рядом. Тест — в задаче 4.
4. **Ошибка загрузки списка стран на странице Create** не должна исчезать при правке имени (она не про попытку создания). Тест — в задаче 3.
5. **Редактор на ширине 390 px** — таблица офферов в карточке потока не должна давать горизонтальную прокрутку страницы. Проверяется в браузере в задаче 6; если ломается — тем же приёмом, что в задаче 5.

---

### Task 1: Баг 1 — Unpin пересчитывает веса, если сумма ≠ 100

**Files:**
- Modify: `backend/app/domain/offer_bindings.py` (`unpin`)
- Modify: `backend/app/services/stream_editor.py` (`unpin_offer`)
- Modify: `docs/decisions.md` (разделы «Что запускает пересчёт весов», «Pin — локальная настройка», при необходимости «Два вида проблемы „сумма не 100“»); `docs/superpowers/specs/2026-11-18-adrobot-design.md` и README — только если там записано старое правило (найти `grep -n -i "unpin\|откреп"`)
- Test: `backend/tests/test_offer_bindings.py`, `backend/tests/test_stream_editor.py`, `backend/tests/test_api_editor.py`

**Interfaces:**
- Produces: `unpin(bindings: Sequence[OfferBinding], binding: OfferBinding) -> None` (было `unpin(binding)`). Остальные вызовы `unpin` в коде и тестах переводятся на новую сигнатуру; `StreamEditor.unpin_offer` идёт через `_apply`, как `pin_offer`.

- [ ] **Step 1: Тесты домена.** В `test_offer_bindings.py`:
  - `test_unpin_recalculates_when_all_pinned_and_sum_is_not_100`: опубликованные 25/25/25, все закреплены; `unpin(bindings, bindings[0])` → веса `[50, 25, 25]`, `bindings[0].is_pinned is False`, `is_draft(bindings) is True`, у `stream_notices(bindings)` нет problems.
  - `test_unpin_recalculates_when_pinned_exceed_100`: опубликованные 60 и 50, оба закреплены; открепили второй → `[60, 40]`.
  - Существующий `test_pin_and_unpin_change_neither_weights_nor_draft_state` (50/50) переводится на новую сигнатуру и по-прежнему проверяет, что при сумме 100 веса и черновик не меняются.
- [ ] **Step 2:** `.venv/Scripts/python -m pytest tests/test_offer_bindings.py -q` — новые тесты падают (TypeError или неверные веса).
- [ ] **Step 3: Реализация.** `unpin` снимает закрепление и вызывает `recalculate(bindings)`, только если `active_total(_slots(_in_order(bindings))) != FULL_WEIGHT`. Комментарий «почему»: иначе подсказка «открепите оффер» не выводит поток из проблемы.
- [ ] **Step 4: Тесты сервиса и API.** В `test_stream_editor.py` — открепление при сумме ≠ 100 меняет веса и делает поток черновиком (сцену подготовить так же, как в соседних тестах). В `test_api_editor.py` — `POST …/offers/{id}/unpin` в такой ситуации возвращает пересчитанные веса, `is_draft: true` и пустые `problems`.
- [ ] **Step 5:** `.venv/Scripts/python -m pytest -q` и `.venv/Scripts/ruff check .` — всё зелёное.
- [ ] **Step 6: Документы.** В `docs/decisions.md` правило звучит так: пересчёт запускают добавление, Remove, Bring back и Unpin, если сумма активных ≠ 100 (пометка «владелец», дата 2026-11-24). В «Pin — локальная настройка»: pin/unpin не делают поток жёлтым, кроме Unpin с пересчётом. Тот же смысл — в спеке и README, если там есть старое правило.
- [ ] **Step 7: Коммит** «Unpin пересчитывает веса, если сумма не 100% (баг 1)».

### Task 2: Баг 6 — одно понятное сообщение для несуществующей кампании

**Files:**
- Modify: `backend/app/services/editor_errors.py` (новый класс), `backend/app/services/campaign_fetcher.py` (`fetch`)
- Modify: `frontend/src/app/editor/editor-view.ts` (`toStatusMessage`)
- Test: `backend/tests/test_campaign_fetcher.py`, `backend/tests/test_api_editor.py`, `frontend/src/app/editor/editor-view.spec.ts`

**Interfaces:**
- Produces: `CampaignNotFoundInKeitaroError(keitaro_campaign_id: int)`, `code = "campaign_not_found_in_keitaro"`, `http_status = 404`, сообщение `f"Кампания {id} не найдена в Keitaro"`.

- [ ] **Step 1: Тесты бэкенда.** Fetch кампании, которой нет в фейковом Keitaro: `CampaignFetcher.fetch` бросает `CampaignNotFoundInKeitaroError` с сообщением «Кампания 99999 не найдена в Keitaro», БД не меняется. API `POST` fetch для 99999 → 404, `code == "campaign_not_found_in_keitaro"`. Если фейковый клиент на неизвестный id не бросает `KeitaroNotFoundError`, научить его этому в `tests/fakes.py` (так ведёт себя реальный клиент на 404).
- [ ] **Step 2:** тесты падают.
- [ ] **Step 3: Реализация.** В `fetch` вокруг `self._client.get_campaign(...)` перехватить `KeitaroNotFoundError` и бросить `CampaignNotFoundInKeitaroError(...) from error`. Перехват только для чтения кампании: 404 на потоки — другая ситуация, её не трогаем.
- [ ] **Step 4: Тест фронтенда** в `editor-view.spec.ts`: `loadStatus: 'not-fetched'`, `pageError: 'Кампания 99999 не найдена в Keitaro'` → `statusMessage === null`, `errorMessage` — этот текст, `showFetchButton === true`. Без ошибки `'not-fetched'` по-прежнему даёт «Кампания N ещё не загружена в редактор».
- [ ] **Step 5: Реализация.** `toStatusMessage`: для `'not-fetched'` вернуть `null`, если `input.pageError !== null` — ошибка Fetch заменяет статус, а не дополняет его.
- [ ] **Step 6:** бэкенд-тесты, ruff, `pnpm test --watch=false`, `pnpm lint` — зелёные.
- [ ] **Step 7: Коммит** «Несуществующая кампания: одно сообщение вместо двух (баг 6)».

### Task 3: Баг 2 — ошибка создания скрывается после правки формы

**Files:**
- Modify: `frontend/src/app/creator/creator-store.ts`
- Modify: `docs/decisions.md` (короткий новый раздел про ошибку Create)
- Test: `frontend/src/app/creator/creator-store.spec.ts`

**Interfaces:**
- `CreatorViewInput.error` и `CreatorView.error` остаются как есть (`string | null`), меняется только то, что store туда подаёт.

- [ ] **Step 1: Тесты** в `creator-store.spec.ts`:
  - после неудачного `submit()` ошибка видна; изменение имени через `store.model.set({...})` → `store.view().error === null`;
  - то же для смены страны и для `store.selectOffer(другой оффер)`;
  - если вернуть ровно те значения, с которыми попытка упала, ошибка снова видна (правило «ошибка относится к этим значениям»);
  - ошибка загрузки списка стран (`countries()` отвечает ошибкой) остаётся видимой после правки имени.
- [ ] **Step 2:** тесты падают.
- [ ] **Step 3: Реализация.** Разделить сигнал `error` на `loadError: string | null` (страны) и `submitFailure: { message: string; attempt: CreateAttempt } | null`, где `CreateAttempt = { name: string; country: string; offerId: number }` (имя после `trim()`, как уходит в API). В `view` подаётся `error = loadError ?? (текст submitFailure, если attempt совпадает с текущими значениями формы, иначе null)`. Сравнение полей — явное, без `Object.*`. Без `effect`: показ ошибки целиком выводится из сигналов.
- [ ] **Step 4:** `pnpm test --watch=false`, `pnpm lint` — зелёные.
- [ ] **Step 5: decisions.md** — раздел «Ошибка создания относится к введённым значениям»: она скрывается, как только имя, страна или оффер отличаются от неудачной попытки. Коммит «Create: ошибка скрывается после исправления полей (баг 2)».

### Task 4: Баг 5 — автокомплит сообщает о пустом результате

**Files:**
- Modify: `frontend/src/app/shared/autocomplete/autocomplete.ts`, `.html`, `.css`
- Modify: `frontend/src/app/editor/stream-card.html` (передать текст про скрытые офферы)
- Test: `frontend/src/app/shared/autocomplete/autocomplete.spec.ts`, `frontend/src/app/editor/stream-card.spec.ts`

**Interfaces:**
- Produces: `Autocomplete.hiddenText = input('')` — текст, когда поиск нашёл варианты, но все они скрыты через `hiddenIds`. Пусто — используется «Ничего не найдено».
- Константа `NOTHING_FOUND_TEXT = 'Ничего не найдено'` в `autocomplete.ts`.

- [ ] **Step 1: Тесты** в `autocomplete.spec.ts`, в стиле существующих (хост-компонент, `type`, `pause`, `requests[i].response.next(...)`):
  - поиск ответил `[]` → в выпадающей области текст «Ничего не найдено», кнопок вариантов нет;
  - поиск вернул только скрытые id, `hiddenText` = «Все найденные офферы уже в потоке» → этот текст; без `hiddenText` → «Ничего не найдено»;
  - поиск упал → только «Поиск недоступен: …», без «Ничего не найдено»;
  - после blur (`focusout` наружу) и после Escape сообщение пропадает, как и список;
  - есть хотя бы один видимый вариант → сообщения нет.
- [ ] **Step 2:** тесты падают.
- [ ] **Step 3: Реализация.** `protected readonly emptyMessage = computed<string | null>(...)`: `null`, если список закрыт (`isOpen()` false), есть видимые варианты или `errorMessage()` не null; иначе `hiddenText() || NOTHING_FOUND_TEXT`, когда `foundOptions()` не пуст (всё скрыто), и `NOTHING_FOUND_TEXT`, когда пуст. В шаблоне сообщение показывается на месте выпадающего списка (абсолютное позиционирование, как `.autocomplete-list`), с `role="status"`, приглушённым цветом.
- [ ] **Step 4:** в `stream-card.html` у автокомплита `hiddenText="Все найденные офферы уже в потоке"`; в `stream-card.spec.ts` — проверка, что текст доходит до автокомплита (поиск вернул только оффер, который уже активен в потоке).
- [ ] **Step 5:** `pnpm test --watch=false`, `pnpm lint` — зелёные. Коммит «Автокомплит: «Ничего не найдено» и «уже в потоке» (баг 5)».

### Task 5: Баги 3 и 4 — пробелы в карточке потока и таблица журнала на телефоне

**Files:**
- Modify: `frontend/src/app/editor/stream-card.html`
- Modify: `frontend/src/app/creator/create-page.html`, `frontend/src/app/creator/create-page.css`
- Test: `frontend/src/app/editor/stream-card.spec.ts`, `frontend/src/app/creator/create-page.spec.ts`

- [ ] **Step 1: Тесты карточки.** Хелпер нормализует `textContent` (`replace(/\s+/g, ' ').trim()`).
  - черновик: текст `h3` равен «Stream 10 #10 черновик» (с данными из `makeStream({ isDraft: true })`);
  - строка оффера с `isPinned: true, isUnpublished: true`: ячейка флагов — «закреплён не опубликован».
- [ ] **Step 2:** тесты падают («#10черновик», «закреплённе опубликован»).
- [ ] **Step 3: Реализация.** Разделитель, который переживает удаление пробелов Angular: `&ngsp;` перед `<em>` и между двумя `<span>` флагов (или эквивалент, при котором тест зелёный и разметка остаётся декларативной). Визуальный отступ только через CSS не годится: в тексте пробела по-прежнему не будет.
- [ ] **Step 4:** `pnpm test --watch=false` зелёный. Коммит «Карточка потока: пробел перед «черновик» и между флагами (баг 3)».
- [ ] **Step 5: Тест журнала.** В `create-page.spec.ts`: таблица `.journal` лежит внутри `.journal-scroll`.
- [ ] **Step 6: Реализация.** Обернуть таблицу журнала в `<div class="journal-scroll">`, в CSS `.journal-scroll { overflow-x: auto; max-width: 100%; }`. Таблица прокручивается внутри своего блока, страница — нет.
- [ ] **Step 7:** `pnpm test --watch=false`, `pnpm lint`, `pnpm build` — зелёные. Коммит «Create: журнал прокручивается внутри своего блока на узком экране (баг 4)».

### Task 6: Итоговая проверка (выполняет координатор, не субагент)

- [ ] **Step 1:** полный прогон: бэкенд `pytest` + `ruff`, фронтенд `test`, `lint`, `build`. Записать числа тестов.
- [ ] **Step 2: Браузер (Playwright MCP).** Демо-стенд (`python -m tools.demo_stand`) + `pnpm start`, без реального Keitaro. Проверить:
  - баг 1: закрепить все офферы потока, получить сумму ≠ 100 (через Remove/Bring back) → Unpin → сумма 100, поток жёлтый, Push доступен;
  - баг 2: имя без префикса → Create → ошибка; исправить имя → ошибка исчезла без нажатия;
  - баг 3: «id N черновик» с пробелом;
  - баг 4: ширина 390 px, страница Create — `document.documentElement.scrollWidth <= 390`; то же для редактора (Review Focus 5);
  - баг 5: «99999» в Offer и «zzz» в кампании → «Ничего не найдено»; оффер, уже стоящий в потоке → «Все найденные офферы уже в потоке»;
  - баг 6: `/editor/99999` + Fetch → одно сообщение «Кампания 99999 не найдена в Keitaro».
- [ ] **Step 3:** `docs/bugs.md` — добавить столбец «Статус» («исправлено», коммит). Закоммитить вместе с планом.
- [ ] **Step 4:** финальное ревью всей ветки (superpowers:requesting-code-review), затем superpowers:finishing-a-development-branch. PR и push — только с согласия владельца.
