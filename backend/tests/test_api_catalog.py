from fastapi.testclient import TestClient

from app.keitaro.errors import KeitaroUnavailableError
from app.main import create_app


def build_client(make_settings, fake) -> TestClient:
    return TestClient(create_app(make_settings(), keitaro_client=fake))


def test_offers_search_returns_id_and_name(make_settings, fake):
    response = build_client(make_settings, fake).get("/api/offers", params={"query": "188"})
    assert response.status_code == 200
    assert response.json() == [{"id": 18813, "name": "Test offer 18813"}]


def test_offers_search_without_query_lists_offers(make_settings, fake):
    response = build_client(make_settings, fake).get("/api/offers")
    assert response.status_code == 200
    assert {"id": 18813, "name": "Test offer 18813"} in response.json()


def test_countries_include_germany(make_settings, fake):
    response = build_client(make_settings, fake).get("/api/countries")
    assert response.status_code == 200
    assert {"code": "DE", "name": "Germany"} in response.json()


def test_offers_search_reports_keitaro_down(make_settings, fake):
    fake.fail("list_offers", KeitaroUnavailableError("Keitaro недоступен: таймаут"))
    response = build_client(make_settings, fake).get("/api/offers", params={"query": "188"})
    assert response.status_code == 502
    assert response.json()["code"] == "keitaro_unavailable"


def test_keitaro_client_is_closed_on_shutdown(make_settings, fake):
    with TestClient(create_app(make_settings(), keitaro_client=fake)):
        assert ("close",) not in fake.calls
    assert ("close",) in fake.calls
