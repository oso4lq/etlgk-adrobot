import logging

import httpx
import pytest

from app.keitaro.errors import (
    KeitaroAuthError,
    KeitaroForbiddenError,
    KeitaroLicenseError,
    KeitaroNotFoundError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.keitaro.http_session import KeitaroHttpSession

API_KEY = "secret-key-123"


def make_session(handler, max_retries=2):
    return KeitaroHttpSession(
        "https://tracker.example.com",
        API_KEY,
        timeout_seconds=5,
        max_retries=max_retries,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )


def test_sends_api_key_to_admin_api_path():
    def handler(request):
        assert request.headers["Api-Key"] == API_KEY
        assert str(request.url) == "https://tracker.example.com/admin_api/v1/groups?type=campaigns"
        return httpx.Response(200, json=[{"id": 1}])

    assert make_session(handler).get("/groups", params={"type": "campaigns"}) == [{"id": 1}]


def test_empty_success_body_returns_none():
    assert (
        make_session(lambda request: httpx.Response(201, content=b"")).delete("/streams/1") is None
    )


@pytest.mark.parametrize(
    ("status", "error_class", "code", "http_status"),
    [
        (401, KeitaroAuthError, "keitaro_auth_failed", 502),
        (402, KeitaroLicenseError, "keitaro_license", 502),
        (403, KeitaroForbiddenError, "keitaro_forbidden", 403),
        (404, KeitaroNotFoundError, "keitaro_not_found", 404),
        (400, KeitaroRejectedError, "keitaro_rejected", 422),
        (406, KeitaroRejectedError, "keitaro_rejected", 422),
        (409, KeitaroRejectedError, "keitaro_rejected", 422),
        (422, KeitaroRejectedError, "keitaro_rejected", 422),
        (500, KeitaroUnavailableError, "keitaro_unavailable", 502),
    ],
)
def test_http_errors_are_mapped(status, error_class, code, http_status):
    session = make_session(
        lambda request: httpx.Response(status, json={"error": "x"}), max_retries=0
    )
    with pytest.raises(error_class) as error:
        session.get("/offers")
    assert (error.value.code, error.value.http_status, error.value.keitaro_status) == (
        code,
        http_status,
        status,
    )


def test_rejected_message_contains_keitaro_text():
    session = make_session(
        lambda request: httpx.Response(400, json={"error": "Alias is already taken"})
    )
    with pytest.raises(KeitaroRejectedError) as error:
        session.post("/campaigns", {"name": "x"})
    assert error.value.message == "Keitaro отклонил запрос: Alias is already taken"


def test_field_errors_are_joined():
    session = make_session(
        lambda request: httpx.Response(406, json={"name": ["Field is required"]})
    )
    with pytest.raises(KeitaroRejectedError) as error:
        session.post("/streams", {})
    assert "name: Field is required" in error.value.message


def test_html_error_body_is_not_echoed():
    html = "<html><head><title>404 Not Found</title></head></html>"
    session = make_session(
        lambda request: httpx.Response(404, text=html, headers={"content-type": "text/html"})
    )
    with pytest.raises(KeitaroNotFoundError) as error:
        session.get("/campaigns/999999999")
    assert "<html" not in error.value.message


def counting(responses):
    """Handler that plays the given responses/exceptions in order and counts attempts."""
    attempts = []

    def handler(request):
        attempts.append(request.method)
        item = responses[min(len(attempts), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    return handler, attempts


def test_get_retries_network_errors_then_succeeds():
    handler, attempts = counting(
        [httpx.ConnectError("down"), httpx.ReadTimeout("slow"), httpx.Response(200, json=[])]
    )
    assert make_session(handler, max_retries=2).get("/offers") == []
    assert len(attempts) == 3


def test_get_gives_up_after_max_retries():
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    with pytest.raises(KeitaroUnavailableError) as error:
        make_session(handler, max_retries=2).get("/offers")
    assert len(attempts) == 3
    assert error.value.message == "Keitaro недоступен: таймаут"


def test_get_retries_on_503():
    handler, attempts = counting([httpx.Response(503), httpx.Response(200, json=[])])
    assert make_session(handler).get("/offers") == []
    assert len(attempts) == 2


def test_write_is_retried_when_connection_failed():
    handler, attempts = counting(
        [httpx.ConnectError("refused"), httpx.Response(200, json={"id": 1})]
    )
    assert make_session(handler).post("/campaigns", {"name": "x"}) == {"id": 1}
    assert len(attempts) == 2


def test_write_is_not_retried_after_read_timeout():
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    with pytest.raises(KeitaroUnavailableError):
        make_session(handler).post("/campaigns", {"name": "x"})
    assert len(attempts) == 1


def test_write_is_not_retried_on_5xx():
    handler, attempts = counting([httpx.Response(503)])
    with pytest.raises(KeitaroUnavailableError):
        make_session(handler).put("/streams/1", {"offers": []})
    assert len(attempts) == 1


def test_api_key_never_leaks(caplog):
    caplog.set_level(logging.DEBUG)
    responses = [
        httpx.Response(200, json=[]),
        httpx.Response(401, json={"error": "Invalid API key"}),
    ]
    handler, _ = counting(responses)
    session = make_session(handler, max_retries=0)
    session.get("/offers")
    with pytest.raises(KeitaroAuthError) as error:
        session.get("/offers")
    assert API_KEY not in caplog.text
    assert API_KEY not in str(error.value) and API_KEY not in repr(error.value)
    assert API_KEY not in repr(session)


def test_key_echoed_by_keitaro_is_redacted():
    session = make_session(
        lambda request: httpx.Response(400, json={"error": f"bad key {API_KEY}"})
    )
    with pytest.raises(KeitaroRejectedError) as error:
        session.get("/offers")
    assert API_KEY not in error.value.message


def test_unavailable_message_hides_tracker_host():
    handler, _ = counting([httpx.ConnectError("cannot connect to tracker.example.com")])
    with pytest.raises(KeitaroUnavailableError) as error:
        make_session(handler, max_retries=0).get("/offers")
    assert "tracker.example.com" not in error.value.message
    assert "tracker.example.com" not in repr(make_session(handler))


def test_from_settings_uses_configured_retries(make_settings):
    handler, attempts = counting([httpx.ReadTimeout("slow")])
    session = KeitaroHttpSession.from_settings(
        make_settings(keitaro_max_retries=0), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(KeitaroUnavailableError):
        session.get("/offers")
    assert len(attempts) == 1


def test_non_json_success_body_is_reported_as_unavailable():
    html = "<html><body>captive portal</body></html>"
    session = make_session(lambda request: httpx.Response(200, text=html))
    with pytest.raises(KeitaroUnavailableError) as error:
        session.get("/offers")
    assert "<html" not in error.value.message
    assert error.value.message == "Keitaro недоступен: некорректный ответ"
    assert error.value.keitaro_status == 200


def test_whitespace_success_body_returns_none():
    assert make_session(lambda request: httpx.Response(200, content=b"\n")).get("/offers") is None


def test_non_transport_request_error_is_reported_as_unavailable():
    handler, attempts = counting([httpx.TooManyRedirects("loop at tracker.example.com")])
    with pytest.raises(KeitaroUnavailableError) as error:
        make_session(handler, max_retries=2).get("/offers")
    assert len(attempts) == 1
    assert error.value.message == "Keitaro недоступен: ошибка сети"
    assert "tracker.example.com" not in error.value.message
