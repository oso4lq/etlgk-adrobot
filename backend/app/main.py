from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_error_handlers
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory: importing this module must not require a .env (tests, tooling)."""
    settings = settings or get_settings()

    app = FastAPI(title="Adrobot")
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    register_error_handlers(app)
    return app
