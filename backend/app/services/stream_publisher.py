"""Push to KT: publish the working offers of one stream to Keitaro.

Only the offers of the stream are written (the rest of the stream is never sent).
Before writing, the service re-checks Keitaro so that manual edits made there are
never overwritten silently. The database is committed only after Keitaro accepted
the change, so a Keitaro failure leaves the draft intact.
Rules: docs/superpowers/specs/2026-11-18-adrobot-design.md sections 5.3 and 5.6.
"""

from app.core.config import Settings
from app.db.models import EditorStream
from app.domain.offer_bindings import (
    active_in_order,
    is_draft,
    mark_published,
    published_shares,
    stream_notices,
    working_shares,
)
from app.domain.write_guard import is_write_allowed
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroNotFoundError
from app.keitaro.models import KeitaroStream, StreamOfferShare
from app.repositories.editor import EditorRepository
from app.services.editor_errors import (
    KeitaroStreamChangedError,
    StreamNotDraftError,
    StreamNotFoundError,
    WeightsNotReadyError,
    WriteForbiddenError,
)
from app.services.remote_offers import remote_offers

STREAM_DELETED_MESSAGE = "Поток удалён в Keitaro — выполните Fetch Streams"
OFFERS_CHANGED_MESSAGE = (
    "Офферы потока в Keitaro изменились после последнего Fetch Streams — выполните Fetch Streams"
)


class StreamPublisher:
    def __init__(self, client: KeitaroClient, settings: Settings) -> None:
        self._client = client
        self._prefix = settings.keitaro_write_name_prefix

    def push(self, repository: EditorRepository, keitaro_stream_id: int) -> EditorStream:
        stream = repository.find_stream(keitaro_stream_id)
        if stream is None:
            raise StreamNotFoundError(keitaro_stream_id)
        campaign = stream.campaign
        if not is_draft(stream.offers):
            raise StreamNotDraftError
        problems = stream_notices(stream.offers).problems
        if problems:
            raise WeightsNotReadyError(problems[0].message)
        if not is_write_allowed(campaign.name, self._prefix):
            raise WriteForbiddenError(self._prefix)

        # The name is read again: the guard protects the shared Keitaro by the campaign's
        # current name, and it may have been changed there after our last Fetch.
        live_campaign = self._client.get_campaign(campaign.keitaro_campaign_id)
        if not is_write_allowed(live_campaign.name, self._prefix):
            raise WriteForbiddenError(self._prefix)

        remote = self._remote_shares(keitaro_stream_id, campaign.keitaro_campaign_id)
        wanted = working_shares(stream.offers)
        # Keitaro already holds exactly our draft: most likely a previous PUT succeeded
        # but its response was lost. Counting it as published avoids a second write.
        if remote != wanted:
            if remote != published_shares(stream.offers):
                raise KeitaroStreamChangedError(OFFERS_CHANGED_MESSAGE)
            self._client.replace_stream_offers(
                keitaro_stream_id,
                [
                    StreamOfferShare(binding.keitaro_offer_id, binding.weight)
                    for binding in active_in_order(stream.offers)
                ],
            )

        mark_published(stream.offers)
        campaign.name = live_campaign.name
        repository.commit()
        return stream

    def _remote_shares(self, keitaro_stream_id: int, keitaro_campaign_id: int) -> dict[int, int]:
        try:
            remote_stream = self._client.get_stream(keitaro_stream_id)
        except KeitaroNotFoundError:
            raise KeitaroStreamChangedError(STREAM_DELETED_MESSAGE) from None
        # An archived stream still answers GET with state "deleted" (decisions В7).
        if remote_stream.state != "active" or remote_stream.campaign_id != keitaro_campaign_id:
            raise KeitaroStreamChangedError(STREAM_DELETED_MESSAGE)
        return _active_shares(remote_stream)


def _active_shares(remote_stream: KeitaroStream) -> dict[int, int]:
    return {
        offer.offer_id: offer.share for offer in remote_offers(remote_stream) if offer.is_active
    }
