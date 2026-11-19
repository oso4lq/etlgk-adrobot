import logging
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.keitaro.errors import (
    KeitaroAliasTakenError,
    KeitaroRejectedError,
    KeitaroUnavailableError,
)
from app.keitaro.http_session import KeitaroHttpSession
from app.keitaro.models import (
    KeitaroCampaign,
    KeitaroDomain,
    KeitaroGroup,
    KeitaroOffer,
    KeitaroStream,
    KeitaroTrafficSource,
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)

logger = logging.getLogger("app.keitaro")


class KeitaroClient(Protocol):
    """What the app needs from Keitaro; tests substitute a fake for the HTTP implementation."""

    def list_offers(self) -> list[KeitaroOffer]: ...
    def list_domains(self) -> list[KeitaroDomain]: ...
    def list_campaign_groups(self) -> list[KeitaroGroup]: ...
    def list_traffic_sources(self) -> list[KeitaroTrafficSource]: ...
    def list_campaigns(self) -> list[KeitaroCampaign]: ...
    def get_campaign(self, campaign_id: int) -> KeitaroCampaign: ...
    def get_campaign_streams(self, campaign_id: int) -> list[KeitaroStream]: ...
    def get_stream(self, stream_id: int) -> KeitaroStream: ...
    def create_campaign(self, campaign: NewCampaign) -> KeitaroCampaign: ...
    def create_country_redirect_stream(self, stream: NewCountryRedirectStream) -> KeitaroStream: ...
    def create_offers_stream(self, stream: NewOffersStream) -> KeitaroStream: ...
    def replace_stream_offers(
        self, stream_id: int, offers: Sequence[StreamOfferShare]
    ) -> KeitaroStream: ...
    def archive_stream(self, stream_id: int) -> None: ...
    def archive_campaign(self, campaign_id: int) -> None: ...
    def close(self) -> None: ...


_OFFERS = TypeAdapter(list[KeitaroOffer])
_DOMAINS = TypeAdapter(list[KeitaroDomain])
_GROUPS = TypeAdapter(list[KeitaroGroup])
_TRAFFIC_SOURCES = TypeAdapter(list[KeitaroTrafficSource])
_STREAMS = TypeAdapter(list[KeitaroStream])
_CAMPAIGN = TypeAdapter(KeitaroCampaign)
_STREAM = TypeAdapter(KeitaroStream)


# Request bodies below are exactly the ones Keitaro accepted during recon
# (docs/keitaro-examples 12, 13, 16, 24); do not add fields without re-checking.
# Creation bodies carry the admin UI defaults from example 24 (see "этап 2" in
# docs/decisions.md) so that a campaign made through the API equals one made by hand.
def _campaign_body(campaign: NewCampaign) -> dict[str, Any]:
    return {
        "name": campaign.name,
        "alias": campaign.alias,
        "type": "position",
        "state": "active",
        "domain_id": campaign.domain_id,
        "group_id": campaign.group_id,
        "traffic_source_id": campaign.traffic_source_id,
        "cost_auto": True,
        "uniqueness_method": "ip_ua",
        "uniqueness_param": "",
        "notes": "",
    }


def _offer_bodies(offers: Sequence[StreamOfferShare]) -> list[dict[str, Any]]:
    return [
        {"offer_id": offer.offer_id, "share": offer.share, "state": "active"} for offer in offers
    ]


def _country_redirect_stream_body(stream: NewCountryRedirectStream) -> dict[str, Any]:
    return {
        "campaign_id": stream.campaign_id,
        "name": stream.name,
        "type": "regular",
        "position": stream.position,
        "weight": 100,
        "comments": "",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": stream.redirect_url,
        "filters": [{"name": "country", "mode": "accept", "payload": [stream.country_code]}],
        "state": "active",
    }


def _offers_stream_body(stream: NewOffersStream) -> dict[str, Any]:
    return {
        "campaign_id": stream.campaign_id,
        "name": stream.name,
        "type": "regular",
        "position": stream.position,
        "weight": 100,
        "comments": "",
        "schema": "landings",
        "action_type": "http",
        "offers": _offer_bodies(stream.offers),
        "state": "active",
    }


def _parse[T](adapter: TypeAdapter[T], payload: Any) -> T:
    """Validates a Keitaro body; a body that does not fit our models is a Keitaro-side failure."""
    try:
        return adapter.validate_python(payload)
    except ValidationError as error:
        # Only field paths are logged: input values may hold foreign data or the tracker host.
        locations = ", ".join(
            ".".join(str(part) for part in item["loc"]) for item in error.errors()
        )
        logger.warning("Keitaro response does not fit the model: %s", locations)
        raise KeitaroUnavailableError("Keitaro недоступен: некорректный ответ") from None


class KeitaroHttpClient:
    def __init__(self, session: KeitaroHttpSession) -> None:
        self._session = session

    @classmethod
    def from_settings(cls, settings: Settings) -> "KeitaroHttpClient":
        return cls(KeitaroHttpSession.from_settings(settings))

    def __enter__(self) -> "KeitaroHttpClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def list_offers(self) -> list[KeitaroOffer]:
        return _parse(_OFFERS, self._session.get("/offers"))

    def list_domains(self) -> list[KeitaroDomain]:
        return _parse(_DOMAINS, self._session.get("/domains"))

    def list_campaign_groups(self) -> list[KeitaroGroup]:
        return _parse(_GROUPS, self._session.get("/groups", {"type": "campaigns"}))

    def list_traffic_sources(self) -> list[KeitaroTrafficSource]:
        return _parse(_TRAFFIC_SOURCES, self._session.get("/traffic_sources"))

    def list_campaigns(self) -> list[KeitaroCampaign]:
        payload = self._session.get("/campaigns")
        if not isinstance(payload, list):
            logger.warning("Keitaro campaign list is not a list")
            raise KeitaroUnavailableError("Keitaro недоступен: некорректный ответ")
        campaigns: list[KeitaroCampaign] = []
        skipped = 0
        for item in payload:
            try:
                campaigns.append(_CAMPAIGN.validate_python(item))
            except ValidationError:
                skipped += 1
        if skipped:
            # The instance is shared: one foreign malformed campaign must not break alias lookup
            # during compensation or campaign choice. Item values are foreign data, so not logged.
            logger.warning("Keitaro campaign list: skipped %d unparseable item(s)", skipped)
        return campaigns

    def get_campaign(self, campaign_id: int) -> KeitaroCampaign:
        return _parse(_CAMPAIGN, self._session.get(f"/campaigns/{campaign_id}"))

    def get_campaign_streams(self, campaign_id: int) -> list[KeitaroStream]:
        return _parse(_STREAMS, self._session.get(f"/campaigns/{campaign_id}/streams"))

    def get_stream(self, stream_id: int) -> KeitaroStream:
        return _parse(_STREAM, self._session.get(f"/streams/{stream_id}"))

    def create_campaign(self, campaign: NewCampaign) -> KeitaroCampaign:
        try:
            created = self._session.post("/campaigns", _campaign_body(campaign))
        except KeitaroRejectedError as error:
            if error.keitaro_status == 422 and "alias" in error.field_names:
                raise KeitaroAliasTakenError(
                    error.message, error.keitaro_status, error.field_names
                ) from None
            raise
        return _parse(_CAMPAIGN, created)

    def create_country_redirect_stream(self, stream: NewCountryRedirectStream) -> KeitaroStream:
        created = self._session.post("/streams", _country_redirect_stream_body(stream))
        return _parse(_STREAM, created)

    def create_offers_stream(self, stream: NewOffersStream) -> KeitaroStream:
        created = self._session.post("/streams", _offers_stream_body(stream))
        return _parse(_STREAM, created)

    def replace_stream_offers(
        self, stream_id: int, offers: Sequence[StreamOfferShare]
    ) -> KeitaroStream:
        # Only `offers` is sent: PUT then leaves every other stream setting untouched (В3).
        updated = self._session.put(f"/streams/{stream_id}", {"offers": _offer_bodies(offers)})
        return _parse(_STREAM, updated)

    def archive_stream(self, stream_id: int) -> None:
        self._session.delete(f"/streams/{stream_id}")

    def archive_campaign(self, campaign_id: int) -> None:
        self._session.delete(f"/campaigns/{campaign_id}")
