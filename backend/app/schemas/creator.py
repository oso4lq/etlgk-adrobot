from datetime import datetime

from pydantic import BaseModel


class CampaignCreateRequest(BaseModel):
    name: str
    country: str
    offer_id: int


class CreatedCampaignResponse(BaseModel):
    journal_id: int
    keitaro_campaign_id: int
    name: str
    alias: str
    campaign_url: str
    country: str
    offer_id: int
    country_stream_id: int
    offers_stream_id: int


class JournalEntryResponse(BaseModel):
    id: int
    name: str
    alias: str | None
    country: str
    offer_id: int
    status: str
    keitaro_campaign_id: int | None
    country_stream_id: int | None
    offers_stream_id: int | None
    campaign_url: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
