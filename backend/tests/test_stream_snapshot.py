import json

import httpx

import tools.stream_snapshot as snapshot_module
from app.keitaro.http_session import KeitaroHttpSession
from tools.stream_snapshot import main, stream_settings_differences

STREAM_ID = 7


def _stream(**overrides) -> dict:
    stream = {
        "id": STREAM_ID,
        "campaign_id": 3,
        "name": "Flow 2",
        "action_payload": None,
        "filters": [{"id": 5, "stream_id": STREAM_ID, "name": "country", "payload": ["DE"]}],
        "offers": [{"offer_id": 1, "share": 100}],
    }
    stream.update(overrides)
    return stream


def _session_builder(current: dict, requests_seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if requests_seen is not None:
            requests_seen.append((request.method, request.url.path))
        return httpx.Response(200, json=current)

    return lambda settings: KeitaroHttpSession.from_settings(
        settings, transport=httpx.MockTransport(handler)
    )


def test_offers_and_empty_action_payload_are_not_differences():
    before = _stream(action_payload=None, offers=[{"offer_id": 1, "share": 100}])
    after = _stream(action_payload="", offers=[])
    assert stream_settings_differences(before, after) == []


def test_changed_filter_is_a_difference():
    after = _stream(
        filters=[{"id": 5, "stream_id": STREAM_ID, "name": "country", "payload": ["FR"]}]
    )
    assert stream_settings_differences(_stream(), after) == [
        "stream.filters[0].payload[0]: эталон 'DE', проверяемая 'FR'"
    ]


def test_changed_filter_id_is_a_difference():
    after = _stream(
        filters=[{"id": 6, "stream_id": STREAM_ID, "name": "country", "payload": ["DE"]}]
    )
    assert stream_settings_differences(_stream(), after) == [
        "stream.filters[0].id: эталон 5, проверяемая 6"
    ]


def test_save_then_diff_round_trip(tmp_path, make_settings, capsys):
    path = tmp_path / "snapshot.json"
    requests_seen: list = []

    save_code = main(
        ["save", str(STREAM_ID), str(path)],
        load_settings=make_settings,
        build_session=_session_builder(_stream(), requests_seen),
    )
    assert save_code == 0
    assert json.loads(path.read_text(encoding="utf-8")) == _stream()

    unchanged_code = main(
        ["diff", str(STREAM_ID), str(path)],
        load_settings=make_settings,
        build_session=_session_builder(_stream(offers=[]), requests_seen),
    )
    assert unchanged_code == 0
    assert "Расхождений нет" in capsys.readouterr().out

    changed_code = main(
        ["diff", str(STREAM_ID), str(path)],
        load_settings=make_settings,
        build_session=_session_builder(_stream(name="Renamed"), requests_seen),
    )
    assert changed_code == 1
    assert "stream.name: эталон 'Flow 2', проверяемая 'Renamed'" in capsys.readouterr().out
    assert {method for method, _ in requests_seen} == {"GET"}
    assert {path for _, path in requests_seen} == {f"/admin_api/v1/streams/{STREAM_ID}"}


def test_diff_record_writes_sanitized_example(tmp_path, make_settings, monkeypatch):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(_stream()), encoding="utf-8")
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    monkeypatch.setattr(snapshot_module, "EXAMPLES_DIR", examples_dir)
    after = _stream(
        action_payload="http://secret-tracker.test/x", comments="key test-secret-key-123"
    )

    code = main(
        ["diff", str(STREAM_ID), str(path), "--record", "recorded"],
        load_settings=lambda: make_settings(keitaro_base_url="https://secret-tracker.test/"),
        build_session=_session_builder(after),
    )

    assert code == 1
    text = (examples_dir / "recorded.json").read_text(encoding="utf-8")
    assert "secret-tracker.test" not in text
    assert "test-secret-key-123" not in text
    recorded = json.loads(text)
    assert recorded["title"] == f"Проверка потока {STREAM_ID} до и после Push"
    assert recorded["request"]["path"] == f"/streams/{STREAM_ID}"
    assert recorded["response"]["body"]["action_payload"] == "http://tracker.example.com/x"
    assert recorded["observations"]["before"] == _stream()
    assert recorded["observations"]["differences"]


def test_main_reports_keitaro_error_without_traceback(tmp_path, make_settings, capsys):
    code = main(
        ["save", str(STREAM_ID), str(tmp_path / "snapshot.json")],
        load_settings=make_settings,
        build_session=lambda settings: KeitaroHttpSession.from_settings(
            settings, transport=httpx.MockTransport(lambda request: httpx.Response(401))
        ),
    )
    assert code == 1
    error_output = capsys.readouterr().err
    assert "Ошибка Keitaro: Неверный ключ API Keitaro" in error_output
    assert "Traceback" not in error_output
    assert not (tmp_path / "snapshot.json").exists()


def test_main_reports_configuration_error_by_names_only(tmp_path, capsys):
    code = main(
        ["save", str(STREAM_ID), str(tmp_path / "snapshot.json")],
        load_settings=lambda: snapshot_module.Settings(
            _env_file=None, keitaro_api_key="secret-xyz"
        ),
    )
    assert code == 2
    error_output = capsys.readouterr().err
    assert "Ошибка конфигурации" in error_output
    assert "secret-xyz" not in error_output


def test_diff_with_missing_snapshot_reports_and_returns_2(tmp_path, make_settings, capsys):
    code = main(
        ["diff", str(STREAM_ID), str(tmp_path / "absent.json")],
        load_settings=make_settings,
        build_session=_session_builder(_stream()),
    )
    assert code == 2
    assert "Не удалось прочитать снимок" in capsys.readouterr().err


def test_diff_with_corrupt_snapshot_reports_and_returns_2(tmp_path, make_settings, capsys):
    path = tmp_path / "snapshot.json"
    path.write_text("{not json", encoding="utf-8")
    code = main(
        ["diff", str(STREAM_ID), str(path)],
        load_settings=make_settings,
        build_session=_session_builder(_stream()),
    )
    assert code == 2
    assert "повреждён" in capsys.readouterr().err


def test_save_to_unwritable_path_reports_and_returns_2(tmp_path, make_settings, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    code = main(
        ["save", str(STREAM_ID), str(blocker / "snapshot.json")],
        load_settings=make_settings,
        build_session=_session_builder(_stream()),
    )
    assert code == 2
    assert "Не удалось записать снимок" in capsys.readouterr().err
