from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import create_app


def test_health_ok(make_settings):
    client = TestClient(create_app(make_settings()))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_error(make_settings):
    app = create_app(make_settings())

    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("db is down"))

    app.state.engine = BrokenEngine()
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "error"}


def test_cors_allows_frontend_origin(make_settings):
    client = TestClient(create_app(make_settings()))
    response = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"
