import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.keitaro.errors import KeitaroRejectedError
from app.main import create_app


@pytest.fixture
def make_api(make_settings, fake):
    def build(**setting_overrides) -> TestClient:
        settings_values = {
            "keitaro_write_name_prefix": "test_oso4lq_",
            "campaign_domain": "kylovoa.com",
            "campaign_group": "FORTESTS",
            "campaign_traffic_source": "FORTESTS",
        }
        settings_values.update(setting_overrides)
        app = create_app(make_settings(**settings_values), keitaro_client=fake)
        Base.metadata.create_all(app.state.engine)
        return TestClient(app)

    return build


@pytest.fixture
def api(make_api) -> TestClient:
    return make_api()


def create_campaign(api: TestClient, name: str = "test_oso4lq_api"):
    return api.post("/api/campaigns", json={"name": name, "country": "de", "offer_id": 18813})


def test_create_campaign_returns_what_was_created(api):
    response = api.post(
        "/api/campaigns", json={"name": "test_oso4lq_api", "country": "de", "offer_id": 18813}
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["country"], body["offer_id"]) == ("test_oso4lq_api", "DE", 18813)
    assert body["campaign_url"] == f"https://kylovoa.com/{body['alias']}"
    assert body["journal_id"] == 1


def test_create_campaign_validation_error_has_code_and_message(api):
    response = api.post(
        "/api/campaigns", json={"name": "test_oso4lq_api", "country": "XX", "offer_id": 18813}
    )
    assert response.status_code == 422
    assert response.json() == {"code": "unknown_country", "message": "Неизвестный код страны: XX"}


def test_keitaro_failure_during_creation_is_not_500(api, fake):
    fake.fail("create_offers_stream", KeitaroRejectedError("Keitaro отклонил запрос: x", 422))
    response = create_campaign(api)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "keitaro_rejected"
    assert body["message"].startswith("Кампания не создана")


def test_journal_lists_created_and_failed_newest_first(api, fake):
    assert create_campaign(api, "test_oso4lq_first").status_code == 201
    fake.fail("create_offers_stream", KeitaroRejectedError("Keitaro отклонил запрос: x", 422))
    assert create_campaign(api, "test_oso4lq_second").status_code == 422

    response = api.get("/api/created-campaigns")
    assert response.status_code == 200
    entries = response.json()
    assert [entry["status"] for entry in entries] == ["failed", "created"]
    assert entries[1]["name"] == "test_oso4lq_first"
    assert entries[0]["error"].startswith("Кампания не создана")
    assert "T" in entries[0]["created_at"]


def test_misconfigured_creator_answers_503(make_api):
    api = make_api(campaign_group="NOPE")
    response = create_campaign(api)
    assert response.status_code == 503
    assert response.json()["code"] == "creator_misconfigured"


def test_wrong_field_type_answers_invalid_request(api):
    response = api.post(
        "/api/campaigns", json={"name": "test_oso4lq_x", "country": "DE", "offer_id": "abc"}
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Некорректный запрос: неверные или отсутствующие поля offer_id",
    }


def test_missing_fields_are_listed_in_order(api):
    response = api.post("/api/campaigns", json={"country": "DE"})
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Некорректный запрос: неверные или отсутствующие поля name, offer_id",
    }


@pytest.mark.parametrize(
    ("content", "headers"),
    [
        (b'{"name": ', {"content-type": "application/json"}),
        (b"[1, 2]", {"content-type": "application/json"}),
    ],
)
def test_malformed_or_non_object_body_has_generic_message(api, content, headers):
    response = api.post("/api/campaigns", content=content, headers=headers)

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Некорректный запрос: тело запроса не разобрано",
    }


def test_too_long_name_is_rejected_before_any_write(api, fake):
    response = create_campaign(api, "test_oso4lq_" + "x" * 244)

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Некорректный запрос: неверные или отсутствующие поля name",
    }
    assert not [call for call in fake.calls if call[0].startswith("create")]
    assert api.get("/api/created-campaigns").json() == []


def test_name_of_255_characters_is_accepted(api):
    assert create_campaign(api, "test_oso4lq_" + "x" * 243).status_code == 201


def test_journal_failure_after_campaign_answers_json(make_settings, fake, monkeypatch):
    from app.repositories.created_campaigns import CreatedCampaignsRepository

    original_save = CreatedCampaignsRepository.save
    saves = []

    def failing_first_save(self, entry):
        saves.append(entry.id)
        if len(saves) == 1:
            entry.name = None  # NOT NULL violation on flush
        try:
            original_save(self, entry)
        finally:
            entry.name = "test_oso4lq_api"

    monkeypatch.setattr(CreatedCampaignsRepository, "save", failing_first_save)
    settings = make_settings(
        keitaro_write_name_prefix="test_oso4lq_",
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
    )
    app = create_app(settings, keitaro_client=fake)
    Base.metadata.create_all(app.state.engine)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/campaigns", json={"name": "test_oso4lq_api", "country": "de", "offer_id": 18813}
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Кампания не создана: внутренняя ошибка. Созданное в Keitaro перенесено в архив",
    }
    assert fake.campaigns[1].state == "deleted"
