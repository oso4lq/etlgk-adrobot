import json
import re

import httpx

from tools.keitaro_examples import (
    EXAMPLES_DIR,
    CreatedObjects,
    changed_fields,
    keep_only_ids,
    redact_fields,
    sanitize,
    write_example,
)


def test_sanitize_replaces_secrets_in_nested_values():
    data = {"url": "https://tracker.real.io/x", "items": [{"note": "key=abc123"}], "count": 5}
    result = sanitize(data, {"tracker.real.io": "tracker.example.com", "abc123": "***"})
    assert result == {
        "url": "https://tracker.example.com/x",
        "items": [{"note": "key=***"}],
        "count": 5,
    }


def test_sanitize_skips_empty_replacement_keys():
    assert sanitize({"text": "value"}, {"": "***"}) == {"text": "value"}


def test_keep_only_ids_drops_foreign_items():
    assert keep_only_ids([{"id": 1, "name": "ours"}, {"id": 2, "name": "foreign"}], {1}) == [
        {"id": 1, "name": "ours"}
    ]


def test_redact_fields_hides_only_listed_non_empty_values():
    items = [
        {"id": 1, "default_campaign": "foreign", "default_campaign_id": 5},
        {"id": 2, "default_campaign": None},
    ]
    assert redact_fields(items, {"default_campaign"}) == [
        {"id": 1, "default_campaign": "***", "default_campaign_id": 5},
        {"id": 2, "default_campaign": None},
    ]


def test_redact_fields_masks_text_inside_nested_values_keeping_shape():
    items = [
        {
            "id": 1,
            "action_options": {"folder": "owner_folder", "retries": 3},
            "country": ["Atlantis"],
            "group_id": 7,
        }
    ]
    assert redact_fields(items, {"action_options", "country", "group_id"}) == [
        {
            "id": 1,
            "action_options": {"folder": "***", "retries": 3},
            "country": ["***"],
            "group_id": 7,
        }
    ]


def test_changed_fields_ignores_listed_keys():
    before = {"name": "Probe", "filters": [1], "updated_at": "a", "offers": []}
    after = {"name": "Probe", "filters": [], "updated_at": "b", "offers": [1]}
    assert changed_fields(before, after, ignore={"updated_at", "offers"}) == {"filters": ([1], [])}


def test_write_example_writes_utf8_json(tmp_path):
    path = write_example(
        tmp_path,
        "10-create-campaign",
        title="Создание",
        request={"method": "POST", "path": "/campaigns", "query": {}, "body": {}},
        response={"status": 200, "body": {"id": 1}},
    )
    assert path == tmp_path / "10-create-campaign.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["title"] == "Создание" and saved["response"]["body"] == {"id": 1}


def test_archive_all_deletes_streams_before_campaigns():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    created = CreatedObjects(campaign_ids=[10], stream_ids=[21, 22])
    with httpx.Client(
        base_url="https://t.example/admin_api/v1", transport=httpx.MockTransport(handler)
    ) as client:
        assert created.archive_all(client) == []
    assert calls == [
        ("DELETE", "/admin_api/v1/streams/21"),
        ("DELETE", "/admin_api/v1/streams/22"),
        ("DELETE", "/admin_api/v1/campaigns/10"),
    ]


def test_archive_all_continues_after_error():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/streams/21"):
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={})

    created = CreatedObjects(campaign_ids=[10], stream_ids=[21])
    with httpx.Client(
        base_url="https://t.example/admin_api/v1", transport=httpx.MockTransport(handler)
    ) as client:
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
