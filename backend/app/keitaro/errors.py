class KeitaroError(Exception):
    """Base class for failures of talking to Keitaro; carries what our API returns to the user."""

    code: str = "keitaro_error"
    http_status: int = 502

    def __init__(self, message: str, keitaro_status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.keitaro_status = keitaro_status


class KeitaroUnavailableError(KeitaroError):
    code = "keitaro_unavailable"
    http_status = 502


class KeitaroAuthError(KeitaroError):
    code = "keitaro_auth_failed"
    http_status = 502


class KeitaroLicenseError(KeitaroError):
    code = "keitaro_license"
    http_status = 502


class KeitaroForbiddenError(KeitaroError):
    code = "keitaro_forbidden"
    http_status = 403


class KeitaroNotFoundError(KeitaroError):
    code = "keitaro_not_found"
    http_status = 404


class KeitaroRejectedError(KeitaroError):
    code = "keitaro_rejected"
    http_status = 422

    def __init__(
        self,
        message: str,
        keitaro_status: int | None = None,
        field_names: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(message, keitaro_status)
        # Fields Keitaro complained about; lets callers react without parsing the message text.
        self.field_names = field_names


class KeitaroAliasTakenError(KeitaroRejectedError):
    """Campaign alias is already used by another campaign (Keitaro answers 422 with `alias`)."""
