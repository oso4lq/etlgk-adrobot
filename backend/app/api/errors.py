from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.keitaro.errors import KeitaroError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(KeitaroError)
    def handle_keitaro_error(request: Request, exc: KeitaroError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
        )
