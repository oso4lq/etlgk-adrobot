from collections.abc import Callable, Sequence
from itertools import count

from app.keitaro.errors import KeitaroNotFoundError
from app.keitaro.models import (
    KeitaroCampaign,
    KeitaroDomain,
    KeitaroGroup,
    KeitaroOffer,
    KeitaroStream,
    KeitaroStreamOffer,
    KeitaroTrafficSource,
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)

DELETED = "deleted"


def _not_found() -> KeitaroNotFoundError:
    return KeitaroNotFoundError("Объект не найден в Keitaro", 404)


def _stream_offers(offers: Sequence[StreamOfferShare]) -> list[KeitaroStreamOffer]:
    return [
        KeitaroStreamOffer(offer_id=offer.offer_id, share=offer.share, state="active")
        for offer in offers
    ]


class FakeKeitaroClient:
    """In-memory KeitaroClient: state is public so tests can arrange and inspect it."""

    def __init__(self) -> None:
        self.offers = [KeitaroOffer(id=18813, name="Test offer 18813", state="active")]
        self.domains = [KeitaroDomain(id=1813, name="kylovoa.com", state="active")]
        self.groups = [KeitaroGroup(id=10332, name="FORTESTS", type="campaigns")]
        self.traffic_sources = [KeitaroTrafficSource(id=836, name="FORTESTS", state="active")]
        self.campaigns: dict[int, KeitaroCampaign] = {}
        self.streams: dict[int, KeitaroStream] = {}
        # `None` models a Keitaro answer without a domain.
        self.campaign_domain: str | None = "https://kylovoa.com/"
        self.calls: list[tuple] = []
        self._campaign_ids = count(1)
        self._stream_ids = count(1)
        self._failures: dict[str, list[tuple[Exception, bool]]] = {}

    def fail(
        self,
        method: str,
        error: Exception,
        *,
        times: int = 1,
        after_applying: bool = False,
    ) -> None:
        """Makes the next `times` calls of `method` raise `error`.

        With `after_applying` the change is made first, like a response timeout after Keitaro
        has already created the object.
        """
        self._failures.setdefault(method, []).extend([(error, after_applying)] * times)

    def _run[T](self, method: str, arguments: tuple, apply: Callable[[], T]) -> T:
        self.calls.append((method, *arguments))
        pending = self._failures.get(method)
        failure = pending.pop(0) if pending else None
        if failure is not None and not failure[1]:
            raise failure[0]
        result = apply()
        if failure is not None:
            raise failure[0]
        return result

    def list_offers(self) -> list[KeitaroOffer]:
        return self._run("list_offers", (), lambda: list(self.offers))

    def list_domains(self) -> list[KeitaroDomain]:
        return self._run("list_domains", (), lambda: list(self.domains))

    def list_campaign_groups(self) -> list[KeitaroGroup]:
        return self._run("list_campaign_groups", (), lambda: list(self.groups))

    def list_traffic_sources(self) -> list[KeitaroTrafficSource]:
        return self._run("list_traffic_sources", (), lambda: list(self.traffic_sources))

    def list_campaigns(self) -> list[KeitaroCampaign]:
        # Archived campaigns are not listed, as in real Keitaro (decisions В7).
        return self._run(
            "list_campaigns",
            (),
            lambda: [c for c in self.campaigns.values() if c.state != DELETED],
        )

    def get_campaign(self, campaign_id: int) -> KeitaroCampaign:
        def apply() -> KeitaroCampaign:
            campaign = self.campaigns.get(campaign_id)
            if campaign is None or campaign.state == DELETED:
                raise _not_found()
            return campaign

        return self._run("get_campaign", (campaign_id,), apply)

    def get_campaign_streams(self, campaign_id: int) -> list[KeitaroStream]:
        def apply() -> list[KeitaroStream]:
            found = [
                stream
                for stream in self.streams.values()
                if stream.campaign_id == campaign_id and stream.state != DELETED
            ]
            return sorted(found, key=lambda stream: stream.position)

        return self._run("get_campaign_streams", (campaign_id,), apply)

    def get_stream(self, stream_id: int) -> KeitaroStream:
        def apply() -> KeitaroStream:
            stream = self.streams.get(stream_id)
            if stream is None:
                raise _not_found()
            return stream

        return self._run("get_stream", (stream_id,), apply)

    def create_campaign(self, campaign: NewCampaign) -> KeitaroCampaign:
        def apply() -> KeitaroCampaign:
            created = KeitaroCampaign(
                id=next(self._campaign_ids),
                name=campaign.name,
                alias=campaign.alias,
                type="position",
                state="active",
                domain=self.campaign_domain,
                domain_id=campaign.domain_id,
                group_id=campaign.group_id,
                traffic_source_id=campaign.traffic_source_id,
            )
            self.campaigns[created.id] = created
            return created

        return self._run("create_campaign", (campaign.alias,), apply)

    def create_country_redirect_stream(self, stream: NewCountryRedirectStream) -> KeitaroStream:
        return self._run(
            "create_country_redirect_stream",
            (stream,),
            lambda: self._add_stream(stream.campaign_id, stream.name, stream.position, "redirect"),
        )

    def create_offers_stream(self, stream: NewOffersStream) -> KeitaroStream:
        return self._run(
            "create_offers_stream",
            (stream,),
            lambda: self._add_stream(
                stream.campaign_id, stream.name, stream.position, "landings", stream.offers
            ),
        )

    def replace_stream_offers(
        self, stream_id: int, offers: Sequence[StreamOfferShare]
    ) -> KeitaroStream:
        def apply() -> KeitaroStream:
            stream = self.streams.get(stream_id)
            if stream is None:
                raise _not_found()
            stream.offers = _stream_offers(offers)
            return stream

        return self._run("replace_stream_offers", (stream_id, tuple(offers)), apply)

    def archive_stream(self, stream_id: int) -> None:
        def apply() -> None:
            stream = self.streams.get(stream_id)
            if stream is None:
                raise _not_found()
            stream.state = DELETED

        self._run("archive_stream", (stream_id,), apply)

    def archive_campaign(self, campaign_id: int) -> None:
        def apply() -> None:
            campaign = self.campaigns.get(campaign_id)
            if campaign is None:
                raise _not_found()
            campaign.state = DELETED

        self._run("archive_campaign", (campaign_id,), apply)

    def close(self) -> None:
        self.calls.append(("close",))

    def _add_stream(
        self,
        campaign_id: int,
        name: str,
        position: int,
        flow_schema: str,
        offers: Sequence[StreamOfferShare] = (),
    ) -> KeitaroStream:
        created = KeitaroStream(
            id=next(self._stream_ids),
            campaign_id=campaign_id,
            name=name,
            type="regular",
            position=position,
            state="active",
            schema=flow_schema,
            action_type="http",
            offers=_stream_offers(offers),
        )
        self.streams[created.id] = created
        return created
