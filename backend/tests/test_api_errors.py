import logging

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.keitaro.errors import (
    KeitaroAuthError,
    KeitaroNotFoundError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.main import create_app


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (KeitaroUnavailableError("Keitaro недоступен: таймаут"), 502, "keitaro_unavailable"),
        (KeitaroAuthError("Неверный ключ API Keitaro"), 502, "keitaro_auth_failed"),
        (KeitaroNotFoundError("Объект не найден в Keitaro"), 404, "keitaro_not_found"),
        (KeitaroRejectedError("Keitaro отклонил запрос: Alias is taken"), 422, "keitaro_rejected"),
    ],
)
def test_keitaro_errors_become_json_responses(make_settings, error, status, code):
    app = create_app(make_settings())

    @app.get("/api/test-keitaro-error")
    def raise_error():
        raise error

    response = TestClient(app).get("/api/test-keitaro-error")
    assert response.status_code == status
    assert response.json() == {"code": code, "message": error.message}


def test_app_error_becomes_json_response(make_settings):
    class TeapotError(AppError):
        code = "x"
        http_status = 418

    app = create_app(make_settings())

    @app.get("/api/test-app-error")
    def raise_error():
        raise TeapotError("я чайник")

    response = TestClient(app).get("/api/test-app-error")
    assert response.status_code == 418
    assert response.json() == {"code": "x", "message": "я чайник"}


def test_create_app_keeps_http_library_logs_clamped(make_settings):
    create_app(make_settings())
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
