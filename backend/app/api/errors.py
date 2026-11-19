from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AppError

# The first location part only says where the field came from, which the user does not need.
_LOCATION_SOURCES = {"body", "query", "path"}


def register_error_handlers(app: FastAPI) -> None:
    # KeitaroError and the creator's errors are all AppError: one handler keeps the format uniform.
    @app.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Input values are left out of the message: they may contain anything.
        fields: list[str] = []
        for error in exc.errors():
            location = list(error["loc"])
            if location and location[0] in _LOCATION_SOURCES:
                location = location[1:]
            field = ".".join(str(part) for part in location)
            if field and field not in fields:
                fields.append(field)
        message = "Некорректный запрос: неверные или отсутствующие поля " + ", ".join(fields)
        return JSONResponse(
            status_code=422, content={"code": "invalid_request", "message": message}
        )
