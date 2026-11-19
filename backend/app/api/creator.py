from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_campaign_creator, get_db_session
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.schemas.creator import (
    CampaignCreateRequest,
    CreatedCampaignResponse,
    JournalEntryResponse,
)
from app.services.campaign_creator import CampaignCreator, CampaignRequest

router = APIRouter(prefix="/api")


@router.post("/campaigns", status_code=201, response_model=CreatedCampaignResponse)
def create_campaign(
    payload: CampaignCreateRequest,
    creator: Annotated[CampaignCreator, Depends(get_campaign_creator)],
    session: Annotated[Session, Depends(get_db_session)],
) -> CreatedCampaignResponse:
    entry = creator.create(
        CreatedCampaignsRepository(session),
        CampaignRequest(name=payload.name, country=payload.country, offer_id=payload.offer_id),
    )
    return CreatedCampaignResponse(
        journal_id=entry.id,
        keitaro_campaign_id=entry.keitaro_campaign_id,
        name=entry.name,
        alias=entry.alias,
        campaign_url=entry.campaign_url,
        country=entry.country,
        offer_id=entry.offer_id,
        country_stream_id=entry.country_stream_id,
        offers_stream_id=entry.offers_stream_id,
    )


@router.get("/created-campaigns", response_model=list[JournalEntryResponse])
def list_created_campaigns(
    session: Annotated[Session, Depends(get_db_session)],
) -> list[JournalEntryResponse]:
    entries = CreatedCampaignsRepository(session).list_recent()
    return [JournalEntryResponse.model_validate(entry, from_attributes=True) for entry in entries]
