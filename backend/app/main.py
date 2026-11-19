from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, creator, health
from app.api.errors import register_error_handlers
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.keitaro.client import KeitaroClient, KeitaroHttpClient
from app.services.campaign_creator import CampaignCreator
from app.services.creator_references import CreatorReferenceResolver
from app.services.offer_catalog import OfferCatalog


def create_app(
    settings: Settings | None = None, keitaro_client: KeitaroClient | None = None
) -> FastAPI:
    """Application factory: importing this module must not require a .env (tests, tooling)."""
    settings = settings or get_settings()
    # Building the real client makes no network calls, so tests may omit the fake.
    keitaro_client = keitaro_client or KeitaroHttpClient.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            keitaro_client.close()

    app = FastAPI(title="Adrobot", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.keitaro_client = keitaro_client
    app.state.offer_catalog = OfferCatalog(keitaro_client, settings.offers_cache_ttl_seconds)
    app.state.campaign_creator = CampaignCreator(
        keitaro_client,
        app.state.offer_catalog,
        CreatorReferenceResolver(keitaro_client, settings),
        settings,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(creator.router)
    app.include_router(catalog.router)
    register_error_handlers(app)
    return app
