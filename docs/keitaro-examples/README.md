# Примеры реальных запросов Keitaro Admin API v1

Получены командой `cd backend && python -m tools.keitaro_probe --confirm-writes` (2026-11-18, один запуск). Скрипт читает справочники, создаёт кампанию `test_oso4lq_put_check` с тремя потоками, проверяет `PUT /streams` на потоке `Probe`, затем переносит всё созданное в архив Keitaro (`DELETE`) и печатает итоговую проверку состояния каждого id.

Из списков вырезаны чужие объекты: оставлены только оффер 18813, домен 1813, группа 10332, источник 836 и объекты, созданные скриптом. Адрес трекера заменён на `tracker.example.com`; ключ API, `token` кампании (даёт доступ к Click API), имя чужой кампании в `default_campaign` и группа домена — на `***`. У оффера скрыты данные владельца инстанса (название, группа, гео, партнёрская сеть, папка и пути лендинга): текст заменён на `***`, структура ответа и числовые id сохранены, чтобы пример показывал реальный формат.

Формат файла: `title`; `request` — `method`, `path` (относительно `/admin_api/v1`), `query`, `body` (`null` — запрос без тела); `response` — `status`, `body` (не-JSON — строка до 300 символов); `observations` — данные проверки (чтение до и после, `changed_fields`).

| Файл | Что показывает |
|---|---|
| `01-get-offers.json` | `GET /offers` — формат оффера |
| `02-get-domains.json` | `GET /domains` — формат домена, имя без схемы (`kylovoa.com`) |
| `03-get-campaign-groups.json` | `GET /groups?type=campaigns` — формат группы кампаний |
| `04-get-traffic-sources.json` | `GET /traffic_sources` — формат источника |
| `05-error-invalid-api-key.json` | неверный ключ API → 401 `{"error": "Invalid API key"}` |
| `06-error-not-found.json` | несуществующая кампания → 404, HTML-страница nginx, не JSON |
| `10-create-campaign.json` | `POST /campaigns` — принятое тело и поля, подставленные Keitaro |
| `11-create-campaign-alias-taken.json` | повтор занятого alias → 422 `{"alias": ["Alias has already used"]}` |
| `12-create-stream-country-redirect.json` | `POST /streams` — поток «страна → редирект» (Flow 1) |
| `13-create-stream-offers.json` | `POST /streams` — поток с оффером (Flow 2) |
| `14-create-stream-probe.json` | `POST /streams` — поток с фильтром, комментарием и оффером для проверки PUT |
| `15-get-campaign-streams.json` | `GET /campaigns/{id}/streams` — потоки кампании |
| `16-put-stream-offers-only.json` | `PUT` только с `offers`: что ещё меняется в потоке, сохраняется ли id строки оффера |
| `17-put-stream-offers-share-zero.json` | `PUT` с `share: 0` |
| `18-put-stream-offers-empty.json` | `PUT` с `offers: []` — список заменяется целиком |
| `19-put-stream-offers-restore.json` | `PUT` — возврат оффера в пустой поток |
| `20-get-campaigns.json` | `GET /campaigns` — формат кампании в списке, `total_count` |
| `21-delete-stream.json` | `DELETE /streams/{id}` и поток после него |
| `22-delete-campaign.json` | `DELETE /campaigns/{id}`: кампания и её потоки после удаления |
| `23-get-admin-reference-campaign.json` | эталон `test_oso4lq_reference`, собранный руками в админке: кампания, потоки и чем они отличаются от созданных через API (10, 12, 13) |
| `24-create-campaign-admin-defaults.json` | `POST /campaigns` и `POST /streams` с полями, которые админка ставит по умолчанию; результат совпадает с эталоном 23 |
| `25-creator-vs-reference.json` | приёмка этапа 2: кампания, созданная нашей API (`test_oso4lq_creator_check`), сравнена с эталоном 23 поле за полем, расхождений нет |
| `26-editor-push-check.json` | живая проверка редактора: поток с офферами (`test_oso4lq_editor_check`) до первого Push и после всех шагов сценария; кроме офферов ничего не изменилось |

Файлы 23 и 24 получены 2026-11-19 разовой разведкой этапа 2: эталон собран в админке через браузер и прочитан через API, тела с полями админки проверены одним запуском (кампания `test_oso4lq_body_check` и её потоки сразу перенесены в архив). Очистка — та же, что и у остальных файлов.

Файл 25 получен 2026-11-19 командой `python -m tools.compare_campaigns 215193 <id> --record 25-creator-vs-reference`; после сравнения обе тестовые кампании убраны в архив.

Файл 26 получен 2026-11-24 командой `python -m tools.stream_snapshot diff <id> <снимок> --record 26-editor-push-check` (снимок до первого Push сделан `save` и хранится вне репозитория). В отличие от 01–25, снятых с настоящего Keitaro, 26 снят с учебного эмулятора Admin API Keitaro (см. `docs/decisions.md`, раздел «2026-11-24 — переход на эмулятор Keitaro и живая проверка»); кампания оставлена в эмуляторе.
