"""Builds what the editor screen shows; the frontend displays these values as they are."""

from app.db.models import EditorCampaign, EditorStream, StreamOffer
from app.domain.notices import Notice
from app.domain.offer_bindings import is_draft, stream_notices
from app.domain.write_guard import is_write_allowed, write_forbidden_message
from app.schemas.editor import (
    CampaignResponse,
    FetchResponse,
    NoticeResponse,
    OfferBindingResponse,
    StreamResponse,
)
from app.services.campaign_fetcher import FetchResult

WRITE_FORBIDDEN_CODE = "write_forbidden"


def _notice_response(notice: Notice) -> NoticeResponse:
    return NoticeResponse(code=notice.code, message=notice.message)


def _offer_response(binding: StreamOffer) -> OfferBindingResponse:
    return OfferBindingResponse(
        offer_id=binding.keitaro_offer_id,
        name=binding.offer_name,
        status=binding.status,
        weight=binding.weight,
        is_pinned=binding.is_pinned,
        is_published=binding.published_status is not None,
    )


def stream_response(stream: EditorStream, write_prefix: str) -> StreamResponse:
    bindings = sorted(stream.offers, key=lambda binding: binding.sort_order)
    if not bindings:
        # A stream without offers is shown as a plain stream: nothing to publish or cancel.
        return StreamResponse(
            keitaro_stream_id=stream.keitaro_stream_id,
            name=stream.name,
            position=stream.position,
            has_offers=False,
            is_draft=False,
            can_push=False,
            can_cancel=False,
            offers=[],
            problems=[],
            warnings=[],
        )

    draft = is_draft(bindings)
    notices = stream_notices(bindings)
    problems = [_notice_response(notice) for notice in notices.problems]
    if draft and not is_write_allowed(stream.campaign.name, write_prefix):
        problems.append(
            NoticeResponse(code=WRITE_FORBIDDEN_CODE, message=write_forbidden_message(write_prefix))
        )
    return StreamResponse(
        keitaro_stream_id=stream.keitaro_stream_id,
        name=stream.name,
        position=stream.position,
        has_offers=True,
        is_draft=draft,
        can_push=draft and not problems,
        can_cancel=draft,
        offers=[_offer_response(binding) for binding in bindings],
        problems=problems,
        warnings=[_notice_response(notice) for notice in notices.warnings],
    )


def campaign_response(campaign: EditorCampaign, write_prefix: str) -> CampaignResponse:
    return CampaignResponse(
        keitaro_campaign_id=campaign.keitaro_campaign_id,
        name=campaign.name,
        write_allowed=is_write_allowed(campaign.name, write_prefix),
        last_fetched_at=campaign.last_fetched_at,
        streams=[stream_response(stream, write_prefix) for stream in campaign.streams],
    )


def fetch_response(result: FetchResult, write_prefix: str) -> FetchResponse:
    return FetchResponse(
        campaign=campaign_response(result.campaign, write_prefix),
        kept_draft_stream_ids=result.kept_draft_stream_ids,
        notices=[_notice_response(notice) for notice in result.notices],
    )
