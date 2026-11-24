from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NoticeResponse(BaseModel):
    code: str
    message: str


class OfferBindingResponse(BaseModel):
    offer_id: int
    name: str
    status: Literal["active", "removed"]
    weight: int
    is_pinned: bool
    # False for an offer added in the wrapper but not yet pushed to Keitaro.
    is_published: bool


class StreamResponse(BaseModel):
    keitaro_stream_id: int
    name: str
    position: int
    has_offers: bool
    is_draft: bool
    can_push: bool
    can_cancel: bool
    offers: list[OfferBindingResponse]
    problems: list[NoticeResponse]
    warnings: list[NoticeResponse]


class CampaignResponse(BaseModel):
    keitaro_campaign_id: int
    name: str
    write_allowed: bool
    last_fetched_at: datetime
    streams: list[StreamResponse]


class FetchResponse(BaseModel):
    campaign: CampaignResponse
    kept_draft_stream_ids: list[int]
    notices: list[NoticeResponse]


class AddOfferRequest(BaseModel):
    offer_id: int


class KeitaroCampaignResponse(BaseModel):
    id: int
    name: str
