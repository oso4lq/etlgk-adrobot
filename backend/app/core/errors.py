class AppError(Exception):
    """Base class of failures our API reports to the user as `{"code", "message"}`."""

    code: str = "app_error"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
