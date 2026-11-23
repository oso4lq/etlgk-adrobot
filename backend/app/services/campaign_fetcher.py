"""Fetch Streams: reconcile the local copy of a campaign with what Keitaro has now.

Keitaro is only read here. All reads happen before the first database write and
the result is committed once, so a Keitaro failure leaves the database untouched.
Rules: docs/superpowers/specs/2026-11-18-adrobot-design.md section 5.4.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.models import EditorCampaign, EditorStream, StreamOffer
from app.domain.notices import Notice
from app.domain.offer_bindings import cancel_draft, is_draft, next_sort_order
from app.domain.offer_sync import RemoteOffer, merge_remote_offers, remote_state, sync_bindings
from app.keitaro.client import KeitaroClient
from app.keitaro.models import KeitaroStream
from app.repositories.editor import EditorRepository
from app.services.editor_errors import CampaignNotFetchedError
from app.services.offer_catalog import OfferCatalog

OFFER_NAME_FALLBACK = "Оффер {offer_id}"


@dataclass(frozen=True)
class FetchResult:
    campaign: EditorCampaign
    kept_draft_stream_ids: list[int]
    notices: list[Notice]


def _quoted_names(names: list[str]) -> str:
    return ", ".join(f"«{name}»" for name in names)


def _remote_offers(stream: KeitaroStream) -> list[RemoteOffer]:
    return merge_remote_offers(
        RemoteOffer(offer.offer_id, offer.share, offer.state == "active") for offer in stream.offers
    )


class CampaignFetcher:
    def __init__(
        self,
        client: KeitaroClient,
        offer_catalog: OfferCatalog,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._offer_catalog = offer_catalog
        self._clock = clock

    def load(self, repository: EditorRepository, keitaro_campaign_id: int) -> EditorCampaign:
        campaign = repository.find_campaign(keitaro_campaign_id)
        if campaign is None:
            raise CampaignNotFetchedError(keitaro_campaign_id)
        return campaign

    def fetch(
        self, repository: EditorRepository, keitaro_campaign_id: int, *, force: bool = False
    ) -> FetchResult:
        keitaro_campaign = self._client.get_campaign(keitaro_campaign_id)
        keitaro_streams = self._client.get_campaign_streams(keitaro_campaign_id)
        offer_names = self._offer_catalog.names()

        campaign = repository.find_campaign(keitaro_campaign_id)
        if campaign is None:
            campaign = repository.add_campaign(
                keitaro_campaign_id, keitaro_campaign.name, self._clock()
            )
        campaign.name = keitaro_campaign.name
        campaign.last_fetched_at = self._clock()

        local_streams = {stream.keitaro_stream_id: stream for stream in campaign.streams}
        kept_draft_stream_ids: list[int] = []
        kept_draft_names: list[str] = []
        for keitaro_stream in keitaro_streams:
            local_stream = local_streams.get(keitaro_stream.id)
            if local_stream is None:
                campaign.streams.append(self._new_stream(keitaro_stream, offer_names))
                continue
            local_stream.name = keitaro_stream.name
            local_stream.position = keitaro_stream.position
            if is_draft(local_stream.offers) and not force:
                kept_draft_stream_ids.append(keitaro_stream.id)
                kept_draft_names.append(keitaro_stream.name)
                continue
            self._sync_stream(local_stream, keitaro_stream, offer_names)

        notices: list[Notice] = []
        if kept_draft_names:
            notices.append(
                Notice(
                    "draft_streams_kept",
                    "Не обновлены потоки с неопубликованными изменениями: "
                    f"{_quoted_names(kept_draft_names)}. Опубликуйте или отмените изменения "
                    "либо повторите Fetch Streams с отбросом черновиков",
                )
            )
        notices.extend(self._remove_missing_streams(campaign, keitaro_streams))

        repository.commit()
        return FetchResult(campaign, kept_draft_stream_ids, notices)

    @staticmethod
    def _offer_name(offer_names: dict[int, str], offer_id: int) -> str:
        return offer_names.get(offer_id) or OFFER_NAME_FALLBACK.format(offer_id=offer_id)

    def _new_binding(
        self, remote: RemoteOffer, sort_order: int, offer_names: dict[int, str]
    ) -> StreamOffer:
        # An unknown offer disabled in Keitaro must not become active here.
        status, weight = remote_state(remote)
        return StreamOffer(
            keitaro_offer_id=remote.offer_id,
            offer_name=self._offer_name(offer_names, remote.offer_id),
            sort_order=sort_order,
            status=status,
            weight=weight,
            is_pinned=False,
            published_status=status,
            published_weight=weight,
        )

    def _new_stream(
        self, keitaro_stream: KeitaroStream, offer_names: dict[int, str]
    ) -> EditorStream:
        stream = EditorStream(
            keitaro_stream_id=keitaro_stream.id,
            name=keitaro_stream.name,
            position=keitaro_stream.position,
        )
        for sort_order, remote in enumerate(_remote_offers(keitaro_stream)):
            stream.offers.append(self._new_binding(remote, sort_order, offer_names))
        return stream

    def _sync_stream(
        self,
        local_stream: EditorStream,
        keitaro_stream: KeitaroStream,
        offer_names: dict[int, str],
    ) -> None:
        if is_draft(local_stream.offers):
            # Forced fetch: the draft is discarded, so never-published bindings go away.
            for binding in cancel_draft(local_stream.offers):
                local_stream.offers.remove(binding)
        unknown = sync_bindings(local_stream.offers, _remote_offers(keitaro_stream))
        for binding in local_stream.offers:
            name = offer_names.get(binding.keitaro_offer_id)
            if name:
                binding.offer_name = name
        for remote in unknown:
            sort_order = next_sort_order(local_stream.offers)
            local_stream.offers.append(self._new_binding(remote, sort_order, offer_names))

    @staticmethod
    def _remove_missing_streams(
        campaign: EditorCampaign, keitaro_streams: list[KeitaroStream]
    ) -> list[Notice]:
        present_ids = {stream.id for stream in keitaro_streams}
        deleted_names: list[str] = []
        lost_draft_names: list[str] = []
        for local_stream in list(campaign.streams):
            if local_stream.keitaro_stream_id in present_ids:
                continue
            deleted_names.append(local_stream.name)
            if is_draft(local_stream.offers):
                lost_draft_names.append(local_stream.name)
            campaign.streams.remove(local_stream)

        notices: list[Notice] = []
        if deleted_names:
            notices.append(
                Notice(
                    "streams_deleted_in_keitaro",
                    "Потоков больше нет в Keitaro, они убраны из редактора: "
                    f"{_quoted_names(deleted_names)}",
                )
            )
        if lost_draft_names:
            notices.append(
                Notice(
                    "drafts_lost_with_deleted_streams",
                    "Неопубликованные изменения потеряны вместе с удалёнными в Keitaro потоками: "
                    f"{_quoted_names(lost_draft_names)}",
                )
            )
        return notices
