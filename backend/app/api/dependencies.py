from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.campaign_catalog import CampaignCatalog
from app.services.campaign_creator import CampaignCreator
from app.services.campaign_fetcher import CampaignFetcher
from app.services.offer_catalog import OfferCatalog
from app.services.stream_editor import StreamEditor
from app.services.stream_publisher import StreamPublisher


def get_db_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_campaign_creator(request: Request) -> CampaignCreator:
    return request.app.state.campaign_creator


def get_offer_catalog(request: Request) -> OfferCatalog:
    return request.app.state.offer_catalog


def get_campaign_catalog(request: Request) -> CampaignCatalog:
    return request.app.state.campaign_catalog


def get_campaign_fetcher(request: Request) -> CampaignFetcher:
    return request.app.state.campaign_fetcher


def get_stream_editor(request: Request) -> StreamEditor:
    return request.app.state.stream_editor


def get_stream_publisher(request: Request) -> StreamPublisher:
    return request.app.state.stream_publisher


def get_write_prefix(request: Request) -> str:
    return request.app.state.settings.keitaro_write_name_prefix
