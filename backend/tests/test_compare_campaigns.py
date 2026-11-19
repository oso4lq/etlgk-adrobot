import json

import httpx

import tools.compare_campaigns as compare_module
from app.keitaro.http_session import KeitaroHttpSession
from tools.compare_campaigns import campaign_differences, main


def test_admin_reference_matches_admin_default_bodies(keitaro_example):
    reference = keitaro_example("23-get-admin-reference-campaign")
    checked = keitaro_example("24-create-campaign-admin-defaults")
    assert (
        campaign_differences(
            reference["response"]["body"],
            reference["observations"]["streams"],
            checked["observations"]["campaign_after"],
            checked["observations"]["streams_after"],
        )
        == []
    )


def test_api_created_campaign_differs_in_admin_defaults(keitaro_example):
    reference = keitaro_example("23-get-admin-reference-campaign")
    archived = keitaro_example("22-delete-campaign")
    differences = campaign_differences(
        reference["response"]["body"],
        reference["observations"]["streams"],
        archived["response"]["body"][0],
        archived["observations"]["campaign_streams_after"]["body"],
    )
    assert {line.split(":")[0] for line in differences} == {
        "campaign.uniqueness_method",
        "campaign.cost_auto",
        "campaign.notes",
        "campaign.uniqueness_param",
        "campaign.state",
        "stream 1.weight",
        "stream 1.comments",
        "stream 2.weight",
        "stream 2.comments",
    }


def test_difference_line_format_and_nested_path():
    reference_streams = [
        {"position": 1, "name": "A", "filters": [{"name": "country", "payload": ["DE"]}]}
    ]
    candidate_streams = [
        {"position": 1, "name": "A", "filters": [{"name": "country", "payload": ["FR"]}]}
    ]
    differences = campaign_differences(
        {"id": 1, "x": 1, "only_ref": 2},
        reference_streams,
        {"id": 2, "x": 5, "extra": 3},
        candidate_streams,
    )
    assert sorted(differences) == sorted(
        [
            "campaign.x: эталон 1, проверяемая 5",
            "campaign.only_ref: нет в проверяемой",
            "campaign.extra: нет в эталоне",
            "stream 1.filters[0].payload[0]: эталон 'DE', проверяемая 'FR'",
        ]
    )


def test_ignored_fields_are_not_reported():
    reference = {
        "id": 1,
        "alias": "a",
        "name": "n",
        "token": "t",
        "created_at": "x",
        "updated_at": "y",
    }
    candidate = {
        "id": 2,
        "alias": "b",
        "name": "m",
        "token": "u",
        "created_at": "z",
        "updated_at": "w",
    }
    assert campaign_differences(reference, [], candidate, []) == []


def test_stream_name_is_compared_but_stream_id_is_not():
    reference = [{"position": 1, "id": 10, "name": "A"}]
    candidate = [{"position": 1, "id": 99, "name": "B"}]
    assert campaign_differences({}, reference, {}, candidate) == [
        "stream 1.name: эталон 'A', проверяемая 'B'"
    ]


def test_missing_stream_is_reported():
    streams = [{"position": 1, "name": "A"}, {"position": 2, "name": "B"}]
    assert campaign_differences({}, streams, {}, streams[:1]) == ["stream 2: нет в проверяемой"]
    assert campaign_differences({}, streams[:1], {}, streams) == ["stream 2: нет в эталоне"]


def test_streams_are_matched_by_position_not_order():
    first = {"position": 1, "name": "A"}
    second = {"position": 2, "name": "B"}
    assert campaign_differences({}, [first, second], {}, [second, first]) == []


def _session_builder(campaigns_by_id, streams, requests_seen):
    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append((request.method, request.url.path))
        if request.url.path.endswith("/streams"):
            return httpx.Response(200, json=streams)
        campaign_id = int(request.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json=campaigns_by_id[campaign_id])

    return lambda settings: KeitaroHttpSession.from_settings(
        settings, transport=httpx.MockTransport(handler)
    )


def test_main_records_sanitized_example(
    tmp_path, make_settings, monkeypatch, keitaro_example, capsys
):
    reference = keitaro_example("23-get-admin-reference-campaign")
    campaign = {**reference["response"]["body"], "token": "tok-secret"}
    monkeypatch.setattr(compare_module, "EXAMPLES_DIR", tmp_path)
    requests_seen = []

    code = main(
        ["1", "2", "--record", "recorded"],
        load_settings=make_settings,
        build_session=_session_builder(
            {1: campaign, 2: campaign}, reference["observations"]["streams"], requests_seen
        ),
    )

    assert code == 0
    assert "Расхождений нет" in capsys.readouterr().out
    assert {method for method, _ in requests_seen} == {"GET"}
    text = (tmp_path / "recorded.json").read_text(encoding="utf-8")
    assert "tok-secret" not in text
    assert "test-secret-key-123" not in text
    recorded = json.loads(text)
    assert recorded["request"]["path"] == "/campaigns/2"
    assert recorded["response"]["body"]["token"] == "***"
    assert recorded["observations"]["reference"]["campaign"]["token"] == "***"
    assert recorded["observations"]["differences"] == []


def test_main_prints_differences_and_returns_one(make_settings, keitaro_example, capsys):
    reference = keitaro_example("23-get-admin-reference-campaign")
    base = reference["response"]["body"]
    code = main(
        ["1", "2"],
        load_settings=make_settings,
        build_session=_session_builder(
            {1: base, 2: {**base, "notes": "changed"}}, reference["observations"]["streams"], []
        ),
    )
    assert code == 1
    assert "campaign.notes" in capsys.readouterr().out


def test_main_reports_keitaro_error_without_traceback(make_settings, capsys):
    code = main(
        ["1", "2"],
        load_settings=make_settings,
        build_session=lambda settings: KeitaroHttpSession.from_settings(
            settings, transport=httpx.MockTransport(lambda request: httpx.Response(401))
        ),
    )
    assert code == 1
    error_output = capsys.readouterr().err
    assert "Ошибка Keitaro: Неверный ключ API Keitaro" in error_output
    assert "Traceback" not in error_output


def test_main_reports_configuration_error_by_names_only(capsys):
    code = main(
        ["1", "2"],
        load_settings=lambda: compare_module.Settings(_env_file=None, keitaro_api_key="secret-xyz"),
    )
    assert code == 2
    error_output = capsys.readouterr().err
    assert "Ошибка конфигурации" in error_output
    assert "secret-xyz" not in error_output


def test_main_record_hides_bare_tracker_host(tmp_path, make_settings, monkeypatch, keitaro_example):
    reference = keitaro_example("23-get-admin-reference-campaign")
    campaign = reference["response"]["body"]
    streams = [dict(stream) for stream in reference["observations"]["streams"]]
    streams[0]["action_payload"] = "http://secret-tracker.test/x"
    streams[1]["comments"] = "see secret-tracker.test/path"
    monkeypatch.setattr(compare_module, "EXAMPLES_DIR", tmp_path)

    main(
        ["1", "2", "--record", "recorded"],
        load_settings=lambda: make_settings(keitaro_base_url="https://secret-tracker.test/"),
        build_session=_session_builder({1: campaign, 2: campaign}, streams, []),
    )

    text = (tmp_path / "recorded.json").read_text(encoding="utf-8")
    assert "secret-tracker.test" not in text
    assert "http://tracker.example.com/x" in text
