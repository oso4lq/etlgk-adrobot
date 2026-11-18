import logging
import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.keitaro.errors import (
    KeitaroAuthError,
    KeitaroError,
    KeitaroForbiddenError,
    KeitaroLicenseError,
    KeitaroNotFoundError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)

logger = logging.getLogger("app.keitaro")

# httpx logs every request URL at INFO, which would put the tracker address into logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Only a failed connection guarantees that Keitaro has not seen a write request yet.
_CONNECTION_FAILURES = (httpx.ConnectError, httpx.ConnectTimeout)
_RETRYABLE_STATUSES = {502, 503, 504}
_MUTATING_METHODS = {"POST", "PUT", "DELETE"}


class KeitaroHttpSession:
    """Single place that holds the API key and talks HTTP to Keitaro Admin API v1."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float,
        max_retries: int,
        retry_delay_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/admin_api/v1",
            headers={"Api-Key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.BaseTransport | None = None
    ) -> "KeitaroHttpSession":
        return cls(
            settings.keitaro_base_url,
            settings.keitaro_api_key.get_secret_value(),
            timeout_seconds=settings.keitaro_timeout_seconds,
            max_retries=settings.keitaro_max_retries,
            transport=transport,
        )

    def __repr__(self) -> str:
        return "KeitaroHttpSession()"

    def __enter__(self) -> "KeitaroHttpSession":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: Mapping[str, str | int] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        return self._request("POST", path, json=body)

    def put(self, path: str, body: Mapping[str, Any]) -> Any:
        return self._request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        attempts_left = self._max_retries
        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.RequestError as exc:
                reason = "таймаут" if isinstance(exc, httpx.TimeoutException) else "ошибка сети"
                if attempts_left > 0 and self._may_retry_failure(method, exc):
                    attempts_left -= 1
                    self._wait_before_retry(method, path, reason)
                    continue
                logger.warning("Keitaro %s %s failed: %s", method, path, reason)
                # Not chained: the original exception text may contain the tracker host.
                raise KeitaroUnavailableError(f"Keitaro недоступен: {reason}") from None

            if (
                response.status_code in _RETRYABLE_STATUSES
                and method not in _MUTATING_METHODS
                and attempts_left > 0
            ):
                attempts_left -= 1
                self._wait_before_retry(method, path, f"HTTP {response.status_code}")
                continue
            if response.is_success:
                return self._parse_success(response)
            error = self._build_error(response)
            logger.warning("Keitaro %s %s failed: HTTP %s", method, path, response.status_code)
            raise error

    @staticmethod
    def _may_retry_failure(method: str, exc: httpx.RequestError) -> bool:
        # Errors that are not transport failures (decoding, redirect loops) will repeat as is.
        if not isinstance(exc, httpx.TransportError):
            return False
        if method in _MUTATING_METHODS:
            return isinstance(exc, _CONNECTION_FAILURES)
        return True

    def _wait_before_retry(self, method: str, path: str, reason: str) -> None:
        logger.warning("Keitaro %s %s: retry after %s", method, path, reason)
        time.sleep(self._retry_delay_seconds)

    @staticmethod
    def _parse_success(response: httpx.Response) -> Any:
        # Keitaro answers some successful calls (DELETE /streams/{id}) with an empty body.
        if not response.content.strip():
            return None
        try:
            return response.json()
        except ValueError:
            # Usually a proxy or captive page in front of Keitaro; the body is not echoed.
            raise KeitaroUnavailableError(
                "Keitaro недоступен: некорректный ответ", response.status_code
            ) from None

    def _build_error(self, response: httpx.Response) -> KeitaroError:
        status = response.status_code
        if status == 401:
            return KeitaroAuthError("Неверный ключ API Keitaro", status)
        if status == 402:
            return KeitaroLicenseError("Admin API недоступен в этой редакции Keitaro", status)
        if status == 403:
            return KeitaroForbiddenError("Нет доступа к объекту в Keitaro", status)
        if status == 404:
            return KeitaroNotFoundError("Объект не найден в Keitaro", status)
        if status >= 500:
            return KeitaroUnavailableError(f"Keitaro недоступен: HTTP {status}", status)
        text = self._extract_error_text(response)
        message = f"Keitaro отклонил запрос: {text}" if text else "Keitaro отклонил запрос"
        return KeitaroRejectedError(message, status, self._extract_field_names(response))

    @staticmethod
    def _extract_field_names(response: httpx.Response) -> frozenset[str]:
        """Field names of a {"field": ["message", ...]} error body; empty for other shapes."""
        try:
            payload = response.json()
        except ValueError:
            return frozenset()
        if not isinstance(payload, dict):
            return frozenset()
        return frozenset(field for field, messages in payload.items() if isinstance(messages, list))

    def _extract_error_text(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""  # HTML from nginx and the like must not be echoed to the user.
        if not isinstance(payload, dict):
            return ""
        error = payload.get("error")
        if isinstance(error, str):
            text = error
        else:
            parts = []
            for field, messages in payload.items():
                if isinstance(messages, list):
                    messages = ", ".join(str(item) for item in messages)
                parts.append(f"{field}: {messages}")
            text = "; ".join(parts)
        return text.replace(self._api_key, "***")
