import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.main import create_app


@pytest.fixture
def api(make_settings, fake) -> TestClient:
    app = create_app(make_settings(keitaro_write_name_prefix="test_oso4lq_"), keitaro_client=fake)
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


@pytest.fixture
def scene(fake):
    for offer_id in range(1001, 1006):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign("test_oso4lq_editor")
    flow_one = fake.add_stream(campaign.id, "Flow 1", 1)
    flow_two = fake.add_stream(campaign.id, "Flow 2", 2, [(1001, 34), (1002, 33), (1003, 33)])
    return campaign, flow_one, flow_two


def fetch(api, campaign):
    response = api.post(f"/api/editor/campaigns/{campaign.id}/fetch")
    assert response.status_code == 200, response.text
    return response.json()


def offers_url(stream, suffix=""):
    return f"/api/editor/streams/{stream.id}/offers{suffix}"


def weights(stream_body):
    return {offer["offer_id"]: offer["weight"] for offer in stream_body["offers"]}


def test_campaign_picker_searches_by_name_and_id(api, fake):
    first = fake.add_campaign("test_oso4lq_alpha")
    second = fake.add_campaign("other_beta")
    by_name = api.get("/api/keitaro-campaigns", params={"query": "alpha"})
    assert by_name.json() == [{"id": first.id, "name": "test_oso4lq_alpha"}]
    by_id = api.get("/api/keitaro-campaigns", params={"query": str(second.id)})
    assert by_id.json() == [{"id": second.id, "name": "other_beta"}]
    everything = api.get("/api/keitaro-campaigns").json()
    assert [item["id"] for item in everything] == [second.id, first.id]


def test_fetch_returns_plain_and_offers_streams(api, scene):
    campaign, flow_one, flow_two = scene
    body = fetch(api, campaign)
    assert body["kept_draft_stream_ids"] == []
    assert body["notices"] == []
    campaign_body = body["campaign"]
    assert campaign_body["keitaro_campaign_id"] == campaign.id
    assert campaign_body["name"] == "test_oso4lq_editor"
    assert campaign_body["write_allowed"] is True
    assert "T" in campaign_body["last_fetched_at"]
    plain, with_offers = campaign_body["streams"]
    assert plain == {
        "keitaro_stream_id": flow_one.id,
        "name": "Flow 1",
        "position": 1,
        "has_offers": False,
        "is_draft": False,
        "can_push": False,
        "can_cancel": False,
        "offers": [],
        "problems": [],
        "warnings": [],
    }
    assert with_offers["keitaro_stream_id"] == flow_two.id
    assert with_offers["has_offers"] is True
    assert [offer["weight"] for offer in with_offers["offers"]] == [34, 33, 33]
    assert [offer["name"] for offer in with_offers["offers"]] == [
        "Offer 1001",
        "Offer 1002",
        "Offer 1003",
    ]
    for offer in with_offers["offers"]:
        assert offer["status"] == "active"
        assert offer["is_published"] is True
        assert offer["is_pinned"] is False


def test_get_campaign_before_fetch_is_404(api):
    response = api.get("/api/editor/campaigns/777")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "campaign_not_fetched"
    assert body["message"].startswith("Кампания 777 ещё не загружена")


def test_get_campaign_after_fetch(api, scene):
    campaign, _, _ = scene
    fetched = fetch(api, campaign)["campaign"]
    assert api.get(f"/api/editor/campaigns/{campaign.id}").json() == fetched


def test_add_offer_returns_draft_with_weights_summing_to_100(api, scene):
    campaign, _, flow_two = scene
    fetch(api, campaign)
    response = api.post(offers_url(flow_two), json={"offer_id": 1004})
    assert response.status_code == 200
    body = response.json()
    assert sum(weights(body).values()) == 100
    assert (body["is_draft"], body["can_push"], body["can_cancel"]) == (True, True, True)
    assert body["problems"] == []
    added = body["offers"][-1]
    assert (added["offer_id"], added["name"], added["is_published"]) == (1004, "Offer 1004", False)


def test_remove_bring_back_pin_unpin_endpoints(api, scene):
    campaign, _, flow_two = scene
    fetch(api, campaign)

    removed = api.post(offers_url(flow_two, "/1003/remove")).json()
    gone = removed["offers"][2]
    assert (gone["status"], gone["weight"]) == ("removed", 0)
    assert removed["is_draft"] is True
    assert sum(weights(removed).values()) == 100

    back = api.post(offers_url(flow_two, "/1003/bring-back")).json()
    assert back["offers"][2]["status"] == "active"
    assert sum(weights(back).values()) == 100

    pinned = api.post(offers_url(flow_two, "/1001/pin")).json()
    assert pinned["offers"][0]["is_pinned"] is True
    unpinned = api.post(offers_url(flow_two, "/1001/unpin")).json()
    assert unpinned["offers"][0]["is_pinned"] is False


def test_push_and_cancel_endpoints(api, fake, scene):
    campaign, _, flow_two = scene
    fetch(api, campaign)
    api.post(offers_url(flow_two), json={"offer_id": 1004})

    pushed = api.post(f"/api/editor/streams/{flow_two.id}/push")
    assert pushed.status_code == 200
    assert pushed.json()["is_draft"] is False
    assert len(fake.streams[flow_two.id].offers) == 4

    clean_cancel = api.post(f"/api/editor/streams/{flow_two.id}/cancel")
    assert clean_cancel.status_code == 200
    assert clean_cancel.json()["is_draft"] is False

    api.post(offers_url(flow_two, "/1004/remove"))
    cancelled = api.post(f"/api/editor/streams/{flow_two.id}/cancel").json()
    assert cancelled["is_draft"] is False
    assert cancelled["can_cancel"] is False
    assert cancelled["offers"][3]["status"] == "active"


def test_fetch_force_query_parameter(api, fake, scene):
    campaign, _, flow_two = scene
    fetch(api, campaign)
    api.post(offers_url(flow_two), json={"offer_id": 1004})
    fake.set_stream_offers(flow_two.id, [(1001, 50), (1002, 50)])

    kept = api.post(f"/api/editor/campaigns/{campaign.id}/fetch").json()
    assert kept["kept_draft_stream_ids"] == [flow_two.id]
    assert len(kept["notices"]) == 1
    assert kept["campaign"]["streams"][1]["is_draft"] is True

    forced = api.post(f"/api/editor/campaigns/{campaign.id}/fetch", params={"force": "true"}).json()
    assert forced["kept_draft_stream_ids"] == []
    stream = forced["campaign"]["streams"][1]
    assert stream["is_draft"] is False
    # 1003 vanished from Keitaro, so it lies in the archive as removed; 1004 is gone.
    assert weights(stream) == {1001: 50, 1002: 50, 1003: 0}
    assert stream["offers"][2]["status"] == "removed"


def test_draft_in_campaign_without_prefix_cannot_be_pushed(api, fake):
    fake.add_offer(1001, "Offer 1001")
    fake.add_offer(1002, "Offer 1002")
    fake.add_offer(1003, "Offer 1003")
    campaign = fake.add_campaign("other_campaign")
    stream = fake.add_stream(campaign.id, "Flow", 1, [(1001, 50), (1002, 50)])
    fetched = fetch(api, campaign)
    assert fetched["campaign"]["write_allowed"] is False

    added = api.post(offers_url(stream), json={"offer_id": 1003})
    assert added.status_code == 200
    body = added.json()
    assert body["is_draft"] is True
    assert body["can_push"] is False
    assert [problem["code"] for problem in body["problems"]] == ["write_forbidden"]
    assert "test_oso4lq_" in body["problems"][0]["message"]

    pushed = api.post(f"/api/editor/streams/{stream.id}/push")
    assert pushed.status_code == 403
    assert pushed.json()["code"] == "write_forbidden"


def test_editor_errors_have_code_and_message(api, fake, scene):
    campaign, flow_one, flow_two = scene
    fetch(api, campaign)

    plain = api.post(offers_url(flow_one), json={"offer_id": 1004})
    assert plain.status_code == 422
    assert plain.json()["code"] == "stream_without_offers"

    unknown = api.post("/api/editor/streams/9999/cancel")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "stream_not_found"

    missing = api.post(offers_url(flow_two), json={})
    assert missing.status_code == 422
    assert missing.json()["code"] == "invalid_request"

    fake.set_stream_offers(flow_two.id, [(1001, 60), (1002, 60)])
    fetch(api, campaign)
    assert api.post(offers_url(flow_two, "/1001/pin")).status_code == 200
    exceeded = api.post(offers_url(flow_two, "/1002/pin"))
    assert exceeded.status_code == 422
    body = exceeded.json()
    assert body["code"] == "pinned_sum_exceeds_100"
    assert body["message"]


def test_keitaro_conflict_on_push_is_409(api, fake, scene):
    campaign, _, flow_two = scene
    fetch(api, campaign)
    api.post(offers_url(flow_two), json={"offer_id": 1004})
    fake.set_stream_offers(flow_two.id, [(1001, 50), (1002, 50)])
    response = api.post(f"/api/editor/streams/{flow_two.id}/push")
    assert response.status_code == 409
    assert response.json()["code"] == "keitaro_stream_changed"


def test_refetch_lists_streams_in_keitaro_position_order(api, fake, scene):
    campaign, flow_one, flow_two = scene
    fetch(api, campaign)
    # Keitaro inserts a stream at position 1 and shifts the others down.
    fake.streams[flow_one.id].position = 2
    fake.streams[flow_two.id].position = 3
    inserted = fake.add_stream(campaign.id, "Flow 0", 1)
    body = fetch(api, campaign)
    names = [stream["name"] for stream in body["campaign"]["streams"]]
    assert names == ["Flow 0", "Flow 1", "Flow 2"]
    assert body["campaign"]["streams"][0]["keitaro_stream_id"] == inserted.id


def test_weights_problem_blocks_push_but_not_cancel(api, fake):
    for offer_id in (1001, 1002):
        fake.add_offer(offer_id, f"Offer {offer_id}")
    campaign = fake.add_campaign("test_oso4lq_weights")
    stream = fake.add_stream(campaign.id, "Flow", 1, [(1001, 40), (1002, 50)])
    fetch(api, campaign)
    api.post(offers_url(stream, "/1001/pin"))
    api.post(offers_url(stream, "/1002/pin"))
    # The only active offer stays pinned at 40%, so the stream cannot reach 100%.
    body = api.post(offers_url(stream, "/1002/remove")).json()
    assert weights(body)[1001] == 40
    assert body["is_draft"] is True
    assert body["can_push"] is False
    assert body["can_cancel"] is True
    assert "weights_sum_not_100" in [problem["code"] for problem in body["problems"]]
