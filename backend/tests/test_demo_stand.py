import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.keitaro.models import KeitaroStream
from tools.demo_stand import (
    DEMO_CAMPAIGN_NAME,
    FOREIGN_CAMPAIGN_NAME,
    build_demo_app,
    build_demo_keitaro,
    demo_settings,
    prepare_database,
)


@pytest.fixture
def demo(tmp_path):
    app = build_demo_app(prepare_database(tmp_path / "demo.db"))
    with TestClient(app) as client:
        yield client


def offers_of(stream: KeitaroStream) -> list[tuple[int, int]]:
    return [(offer.offer_id, offer.share) for offer in stream.offers]


def test_demo_keitaro_matches_video():
    keitaro = build_demo_keitaro()
    campaigns = {campaign.name: campaign for campaign in keitaro.list_campaigns()}
    assert FOREIGN_CAMPAIGN_NAME in campaigns
    streams = keitaro.get_campaign_streams(campaigns[DEMO_CAMPAIGN_NAME].id)
    assert [stream.position for stream in streams] == [1, 2]
    assert offers_of(streams[0]) == []
    assert offers_of(streams[1]) == [(501, 34), (502, 33), (503, 33)]
    offer_ids = {offer.id for offer in keitaro.list_offers()}
    assert set(range(501, 507)) <= offer_ids


def test_demo_settings_ignore_env_file(monkeypatch):
    monkeypatch.setenv("KEITARO_BASE_URL", "https://real.example")
    monkeypatch.setenv("KEITARO_API_KEY", "real-secret")
    settings = demo_settings("sqlite://")
    assert settings.keitaro_base_url == "https://keitaro.demo.invalid"
    assert settings.keitaro_api_key.get_secret_value() == "demo-stand-not-a-real-key"


def test_prepare_database_recreates_file(tmp_path):
    path = tmp_path / "demo.db"
    path.write_bytes(b"garbage, not a database")
    for _ in range(2):
        url = prepare_database(path)
        assert url.startswith("sqlite:///")
        # sqlite3's own context manager does not close, and Windows would keep the file locked.
        with closing(sqlite3.connect(path)) as connection:
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        assert len(rows) == 1


def test_demo_stream_route_shows_keitaro_state(demo):
    body = demo.get("/demo/keitaro/streams/2").json()
    assert body["schema"] == "landings"
    assert [(offer["offer_id"], offer["share"]) for offer in body["offers"]] == [
        (501, 34),
        (502, 33),
        (503, 33),
    ]
    assert body["total_share"] == 100


def test_demo_delete_route_removes_offer_without_rebalancing(demo):
    # The wrapper has to know the offer before Keitaro loses it.
    demo.post("/api/editor/campaigns/1/fetch")
    body = demo.post("/demo/keitaro/streams/2/offers/502/delete").json()
    assert [(offer["offer_id"], offer["share"]) for offer in body["offers"]] == [
        (501, 34),
        (503, 33),
    ]
    assert body["total_share"] == 67

    fetched = demo.post("/api/editor/campaigns/1/fetch").json()
    offers = {
        offer["offer_id"]: offer["status"] for offer in fetched["campaign"]["streams"][1]["offers"]
    }
    assert offers[502] == "removed"


def test_demo_routes_answer_404_for_unknown_objects(demo):
    for url in ("/demo/keitaro/streams/99", "/demo/keitaro/streams/99/offers/501/delete"):
        response = demo.get(url) if "delete" not in url else demo.post(url)
        assert response.status_code == 404
        assert response.json()["code"] == "demo_not_found"
    missing_offer = demo.post("/demo/keitaro/streams/2/offers/506/delete")
    assert missing_offer.status_code == 404
    assert missing_offer.json()["code"] == "demo_not_found"


def test_demo_stand_runs_add_and_push(demo):
    demo.post("/api/editor/campaigns/1/fetch")
    added = demo.post("/api/editor/streams/2/offers", json={"offer_id": 504})
    assert [offer["weight"] for offer in added.json()["offers"]] == [25, 25, 25, 25]
    assert demo.post("/api/editor/streams/2/push").status_code == 200
    body = demo.get("/demo/keitaro/streams/2").json()
    assert [offer["share"] for offer in body["offers"]] == [25, 25, 25, 25]


def test_demo_stand_refuses_push_to_foreign_campaign(demo):
    demo.post("/api/editor/campaigns/2/fetch")
    removed = demo.post("/api/editor/streams/3/offers/504/remove").json()
    assert removed["can_push"] is False
    assert "write_forbidden" in [problem["code"] for problem in removed["problems"]]
