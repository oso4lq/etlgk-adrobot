from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import TypeAdapter

from app.core.config import Settings
from app.keitaro.errors import KeitaroAliasTakenError, KeitaroRejectedError
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
_CAMPAIGNS = TypeAdapter(list[KeitaroCampaign])
_STREAMS = TypeAdapter(list[KeitaroStream])


# Request bodies below are exactly the ones Keitaro accepted during recon
# (docs/keitaro-examples 10, 12, 13, 16); do not add fields without re-checking.
def _campaign_body(campaign: NewCampaign) -> dict[str, Any]:
    return {
        "name": campaign.name,
        "alias": campaign.alias,
        "type": "position",
        "state": "active",
        "domain_id": campaign.domain_id,
        "group_id": campaign.group_id,
        "traffic_source_id": campaign.traffic_source_id,
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
        "schema": "landings",
        "action_type": "http",
        "offers": _offer_bodies(stream.offers),
        "state": "active",
    }


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
        return _OFFERS.validate_python(self._session.get("/offers"))

    def list_domains(self) -> list[KeitaroDomain]:
        return _DOMAINS.validate_python(self._session.get("/domains"))

    def list_campaign_groups(self) -> list[KeitaroGroup]:
        return _GROUPS.validate_python(self._session.get("/groups", {"type": "campaigns"}))

    def list_traffic_sources(self) -> list[KeitaroTrafficSource]:
        return _TRAFFIC_SOURCES.validate_python(self._session.get("/traffic_sources"))

    def list_campaigns(self) -> list[KeitaroCampaign]:
        return _CAMPAIGNS.validate_python(self._session.get("/campaigns"))

    def get_campaign(self, campaign_id: int) -> KeitaroCampaign:
        return KeitaroCampaign.model_validate(self._session.get(f"/campaigns/{campaign_id}"))

    def get_campaign_streams(self, campaign_id: int) -> list[KeitaroStream]:
        return _STREAMS.validate_python(self._session.get(f"/campaigns/{campaign_id}/streams"))

    def get_stream(self, stream_id: int) -> KeitaroStream:
        return KeitaroStream.model_validate(self._session.get(f"/streams/{stream_id}"))

    def create_campaign(self, campaign: NewCampaign) -> KeitaroCampaign:
        try:
            created = self._session.post("/campaigns", _campaign_body(campaign))
        except KeitaroRejectedError as error:
            if error.keitaro_status == 422 and "alias" in error.field_names:
                raise KeitaroAliasTakenError(
                    error.message, error.keitaro_status, error.field_names
                ) from None
            raise
        return KeitaroCampaign.model_validate(created)

    def create_country_redirect_stream(self, stream: NewCountryRedirectStream) -> KeitaroStream:
        created = self._session.post("/streams", _country_redirect_stream_body(stream))
        return KeitaroStream.model_validate(created)

    def create_offers_stream(self, stream: NewOffersStream) -> KeitaroStream:
        created = self._session.post("/streams", _offers_stream_body(stream))
        return KeitaroStream.model_validate(created)

    def replace_stream_offers(
        self, stream_id: int, offers: Sequence[StreamOfferShare]
    ) -> KeitaroStream:
        # Only `offers` is sent: PUT then leaves every other stream setting untouched (В3).
        updated = self._session.put(f"/streams/{stream_id}", {"offers": _offer_bodies(offers)})
        return KeitaroStream.model_validate(updated)

    def archive_stream(self, stream_id: int) -> None:
        self._session.delete(f"/streams/{stream_id}")

    def archive_campaign(self, campaign_id: int) -> None:
        self._session.delete(f"/campaigns/{campaign_id}")
