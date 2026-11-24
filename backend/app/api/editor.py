from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_campaign_catalog,
    get_campaign_fetcher,
    get_db_session,
    get_stream_editor,
    get_stream_publisher,
    get_write_prefix,
)
from app.repositories.editor import EditorRepository
from app.schemas.editor import (
    AddOfferRequest,
    CampaignResponse,
    FetchResponse,
    KeitaroCampaignResponse,
    StreamResponse,
)
from app.services.campaign_catalog import CampaignCatalog
from app.services.campaign_fetcher import CampaignFetcher
from app.services.editor_views import campaign_response, fetch_response, stream_response
from app.services.stream_editor import StreamEditor
from app.services.stream_publisher import StreamPublisher

router = APIRouter(prefix="/api")

SessionDependency = Annotated[Session, Depends(get_db_session)]
WritePrefix = Annotated[str, Depends(get_write_prefix)]
EditorDependency = Annotated[StreamEditor, Depends(get_stream_editor)]


@router.get("/keitaro-campaigns", response_model=list[KeitaroCampaignResponse])
def search_keitaro_campaigns(
    catalog: Annotated[CampaignCatalog, Depends(get_campaign_catalog)], query: str = ""
) -> list[KeitaroCampaignResponse]:
    return [
        KeitaroCampaignResponse(id=campaign.id, name=campaign.name)
        for campaign in catalog.search(query)
    ]


@router.post("/editor/campaigns/{keitaro_campaign_id}/fetch", response_model=FetchResponse)
def fetch_campaign(
    keitaro_campaign_id: int,
    fetcher: Annotated[CampaignFetcher, Depends(get_campaign_fetcher)],
    session: SessionDependency,
    write_prefix: WritePrefix,
    force: bool = False,
) -> FetchResponse:
    result = fetcher.fetch(EditorRepository(session), keitaro_campaign_id, force=force)
    return fetch_response(result, write_prefix)


@router.get("/editor/campaigns/{keitaro_campaign_id}", response_model=CampaignResponse)
def get_campaign(
    keitaro_campaign_id: int,
    fetcher: Annotated[CampaignFetcher, Depends(get_campaign_fetcher)],
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> CampaignResponse:
    campaign = fetcher.load(EditorRepository(session), keitaro_campaign_id)
    return campaign_response(campaign, write_prefix)


@router.post("/editor/streams/{keitaro_stream_id}/offers", response_model=StreamResponse)
def add_offer(
    keitaro_stream_id: int,
    payload: AddOfferRequest,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.add_offer(EditorRepository(session), keitaro_stream_id, payload.offer_id)
    return stream_response(stream, write_prefix)


@router.post(
    "/editor/streams/{keitaro_stream_id}/offers/{offer_id}/remove", response_model=StreamResponse
)
def remove_offer(
    keitaro_stream_id: int,
    offer_id: int,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.remove_offer(EditorRepository(session), keitaro_stream_id, offer_id)
    return stream_response(stream, write_prefix)


@router.post(
    "/editor/streams/{keitaro_stream_id}/offers/{offer_id}/bring-back",
    response_model=StreamResponse,
)
def bring_back_offer(
    keitaro_stream_id: int,
    offer_id: int,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.bring_back_offer(EditorRepository(session), keitaro_stream_id, offer_id)
    return stream_response(stream, write_prefix)


@router.post(
    "/editor/streams/{keitaro_stream_id}/offers/{offer_id}/pin", response_model=StreamResponse
)
def pin_offer(
    keitaro_stream_id: int,
    offer_id: int,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.pin_offer(EditorRepository(session), keitaro_stream_id, offer_id)
    return stream_response(stream, write_prefix)


@router.post(
    "/editor/streams/{keitaro_stream_id}/offers/{offer_id}/unpin", response_model=StreamResponse
)
def unpin_offer(
    keitaro_stream_id: int,
    offer_id: int,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.unpin_offer(EditorRepository(session), keitaro_stream_id, offer_id)
    return stream_response(stream, write_prefix)


@router.post("/editor/streams/{keitaro_stream_id}/push", response_model=StreamResponse)
def push_stream(
    keitaro_stream_id: int,
    publisher: Annotated[StreamPublisher, Depends(get_stream_publisher)],
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = publisher.push(EditorRepository(session), keitaro_stream_id)
    return stream_response(stream, write_prefix)


@router.post("/editor/streams/{keitaro_stream_id}/cancel", response_model=StreamResponse)
def cancel_stream(
    keitaro_stream_id: int,
    editor: EditorDependency,
    session: SessionDependency,
    write_prefix: WritePrefix,
) -> StreamResponse:
    stream = editor.cancel(EditorRepository(session), keitaro_stream_id)
    return stream_response(stream, write_prefix)
