from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.campaign_creator import CampaignCreator
from app.services.offer_catalog import OfferCatalog


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
