from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import CreatedCampaign, CreationStatus
from app.domain.alias import generate_alias
from app.domain.countries import find_country
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroAliasTakenError
from app.keitaro.models import (
    KeitaroCampaign,
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.services.creator_references import CreatorReferenceResolver, CreatorReferences
from app.services.offer_catalog import OfferCatalog

MAX_ALIAS_ATTEMPTS = 3
COUNTRY_STREAM_NAME = "Flow 1"
OFFERS_STREAM_NAME = "Flow 2"
FULL_SHARE = 100


class InvalidCampaignNameError(AppError):
    code = "invalid_name"
    http_status = 422

    def __init__(self) -> None:
        super().__init__("Название кампании не может быть пустым")


class NamePrefixRequiredError(AppError):
    # 422 rather than 403: it is a form input mistake the user fixes by editing the name.
    code = "name_prefix_required"
    http_status = 422

    def __init__(self, prefix: str) -> None:
        super().__init__(f"Название кампании должно начинаться с «{prefix}»")


class UnknownCountryError(AppError):
    code = "unknown_country"
    http_status = 422

    def __init__(self, country_code: str) -> None:
        super().__init__(f"Неизвестный код страны: {country_code}")


class OfferNotFoundError(AppError):
    code = "offer_not_found"
    http_status = 422

    def __init__(self, offer_id: int) -> None:
        super().__init__(f"Оффер {offer_id} не найден в Keitaro")


class CampaignCreationFailedError(AppError):
    def __init__(self, message: str, code: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class CampaignRequest:
    name: str
    country: str
    offer_id: int


class CampaignCreator:
    def __init__(
        self,
        client: KeitaroClient,
        offers: OfferCatalog,
        references: CreatorReferenceResolver,
        settings: Settings,
        generate_alias: Callable[[], str] = generate_alias,
    ) -> None:
        self._client = client
        self._offers = offers
        self._references = references
        self._settings = settings
        self._generate_alias = generate_alias

    def create(
        self, journal: CreatedCampaignsRepository, request: CampaignRequest
    ) -> CreatedCampaign:
        name = request.name.strip()
        if not name:
            raise InvalidCampaignNameError
        prefix = self._settings.keitaro_write_name_prefix
        if prefix and not name.startswith(prefix):
            raise NamePrefixRequiredError(prefix)
        country = find_country(request.country)
        if country is None:
            raise UnknownCountryError(request.country.strip())
        references = self._references.resolve()
        if self._offers.find(request.offer_id) is None:
            raise OfferNotFoundError(request.offer_id)

        # Everything above is read-only: a rejected request leaves no trace in Keitaro or journal.
        entry = journal.add_pending(name, country.code, request.offer_id)

        campaign = self._create_campaign(name, references, entry, journal)
        country_stream = self._client.create_country_redirect_stream(
            NewCountryRedirectStream(
                campaign_id=campaign.id,
                name=COUNTRY_STREAM_NAME,
                position=1,
                country_code=country.code,
                redirect_url=self._settings.redirect_url,
            )
        )
        # Saved after every step so a crash leaves the ids needed for manual cleanup.
        entry.country_stream_id = country_stream.id
        journal.save(entry)
        offers_stream = self._client.create_offers_stream(
            NewOffersStream(
                campaign_id=campaign.id,
                name=OFFERS_STREAM_NAME,
                position=2,
                offers=(StreamOfferShare(request.offer_id, FULL_SHARE),),
            )
        )
        entry.offers_stream_id = offers_stream.id
        journal.save(entry)

        base = campaign.domain or f"https://{references.domain_name}"
        entry.campaign_url = f"{base.rstrip('/')}/{entry.alias}"
        entry.status = CreationStatus.CREATED
        journal.save(entry)
        return entry

    def _create_campaign(
        self,
        name: str,
        references: CreatorReferences,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
    ) -> KeitaroCampaign:
        attempt = 0
        while True:
            attempt += 1
            alias = self._generate_alias()
            try:
                campaign = self._client.create_campaign(
                    NewCampaign(
                        name=name,
                        alias=alias,
                        domain_id=references.domain_id,
                        group_id=references.group_id,
                        traffic_source_id=references.traffic_source_id,
                    )
                )
            except KeitaroAliasTakenError:
                if attempt >= MAX_ALIAS_ATTEMPTS:
                    raise
                continue
            entry.alias = alias
            entry.keitaro_campaign_id = campaign.id
            journal.save(entry)
            return campaign
