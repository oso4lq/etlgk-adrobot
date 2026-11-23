import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import CreatedCampaign, CreationStatus
from app.domain.alias import generate_alias
from app.domain.countries import find_country
from app.keitaro.client import KeitaroClient
from app.keitaro.errors import KeitaroAliasTakenError, KeitaroUnavailableError
from app.keitaro.models import (
    KeitaroCampaign,
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.services.creator_references import CreatorReferenceResolver, CreatorReferences
from app.services.offer_catalog import OfferCatalog, OfferNotFoundError

logger = logging.getLogger("app.creator")

MAX_ALIAS_ATTEMPTS = 3
COUNTRY_STREAM_NAME = "Flow 1"
OFFERS_STREAM_NAME = "Flow 2"
FULL_SHARE = 100
COMPENSATION_FAILED_CODE = "compensation_failed"
COMPENSATION_FAILED_HTTP_STATUS = 502
INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_HTTP_STATUS = 500
# Fixed text: the raw exception of an unexpected failure may contain anything.
INTERNAL_ERROR_MESSAGE = "внутренняя ошибка"


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


@dataclass(frozen=True)
class _Cause:
    """What the user is told about a failure, whether or not it came from an `AppError`."""

    message: str
    code: str
    http_status: int

    @classmethod
    def of(cls, error: Exception) -> "_Cause":
        if isinstance(error, AppError):
            return cls(error.message, error.code, error.http_status)
        return cls(INTERNAL_ERROR_MESSAGE, INTERNAL_ERROR_CODE, INTERNAL_ERROR_HTTP_STATUS)


@dataclass
class _Progress:
    """What Keitaro has created so far, kept apart from the journal.

    A journal write can fail right after Keitaro answered; compensation must still know what exists.
    """

    alias: str | None = None
    campaign_id: int | None = None
    country_stream_id: int | None = None
    offers_stream_id: int | None = None

    def stream_ids(self) -> set[int]:
        known = (self.country_stream_id, self.offers_stream_id)
        return {stream_id for stream_id in known if stream_id is not None}


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
        # Kept locally: after a failed commit the entry is expired and reading it hits the DB again.
        journal_id = entry.id

        progress = _Progress()
        try:
            campaign = self._create_campaign(name, references, entry, journal, journal_id, progress)
            country_stream = self._client.create_country_redirect_stream(
                NewCountryRedirectStream(
                    campaign_id=campaign.id,
                    name=COUNTRY_STREAM_NAME,
                    position=1,
                    country_code=country.code,
                    redirect_url=self._settings.redirect_url,
                )
            )
            progress.country_stream_id = country_stream.id
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
            progress.offers_stream_id = offers_stream.id
            entry.offers_stream_id = offers_stream.id
            journal.save(entry)

            base = campaign.domain or f"https://{references.domain_name}"
            entry.campaign_url = f"{base.rstrip('/')}/{progress.alias}"
            entry.status = CreationStatus.CREATED
            # Inside the try: a campaign we cannot record must not stay in Keitaro (spec §5).
            journal.save(entry)
        except CampaignCreationFailedError:
            # Already compensated and written to the journal by the campaign step.
            raise
        except Exception as error:
            # A failed save rolls the session back and expires the entry. Only assignments are made
            # here, never reads: with the database still down a read would raise before the
            # compensation below has archived anything.
            entry.alias = progress.alias
            entry.keitaro_campaign_id = progress.campaign_id
            entry.country_stream_id = progress.country_stream_id
            entry.offers_stream_id = progress.offers_stream_id
            entry.campaign_url = None
            raise self._compensate_and_fail(
                entry,
                journal,
                journal_id,
                self._describe(error),
                progress.campaign_id,
                progress.stream_ids(),
            ) from error
        return entry

    @staticmethod
    def _describe(error: Exception) -> _Cause:
        if not isinstance(error, AppError):
            # Keitaro failures are logged by the HTTP session; this is a bug or a database error.
            logger.exception("Unexpected error while creating a campaign", exc_info=error)
        return _Cause.of(error)

    def _create_campaign(
        self,
        name: str,
        references: CreatorReferences,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
        journal_id: int,
        progress: _Progress,
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
            except KeitaroAliasTakenError as error:
                if attempt >= MAX_ALIAS_ATTEMPTS:
                    cause = _Cause(
                        f"Не удалось подобрать свободный alias за {MAX_ALIAS_ATTEMPTS} попытки",
                        error.code,
                        error.http_status,
                    )
                    raise self._finish_with_error(
                        entry,
                        journal,
                        journal_id,
                        CreationStatus.FAILED,
                        f"Кампания не создана: {cause.message}",
                        cause,
                    ) from error
                continue
            except KeitaroUnavailableError as error:
                # The POST may have been executed with the response lost on the way back.
                raise self._fail_unconfirmed_campaign(
                    entry, journal, journal_id, name, alias, _Cause.of(error)
                ) from error
            progress.alias = alias
            progress.campaign_id = campaign.id
            entry.alias = alias
            entry.keitaro_campaign_id = campaign.id
            journal.save(entry)
            return campaign

    def _find_our_campaign(self, name: str, alias: str) -> KeitaroCampaign | None:
        for campaign in self._client.list_campaigns():
            # The name is checked too: only a campaign that is surely ours may be archived.
            if campaign.alias == alias and campaign.name == name:
                return campaign
        return None

    def _fail_unconfirmed_campaign(
        self,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
        journal_id: int,
        name: str,
        alias: str,
        cause: _Cause,
    ) -> CampaignCreationFailedError:
        entry.alias = alias
        try:
            found = self._find_our_campaign(name, alias)
        except Exception:
            # Without the listing we cannot tell whether a campaign is hanging in Keitaro.
            return self._fail_with_leftovers(
                entry,
                journal,
                journal_id,
                cause,
                [f"кампания с alias {alias} (проверить, создалась ли, не удалось)"],
            )
        if found is None:
            return self._finish_with_error(
                entry,
                journal,
                journal_id,
                CreationStatus.FAILED,
                f"Кампания не создана: {cause.message}. "
                f"Кампания с alias {alias} в Keitaro не найдена",
                cause,
            )
        entry.keitaro_campaign_id = found.id
        return self._compensate_and_fail(entry, journal, journal_id, cause, found.id, set())

    def _compensate_and_fail(
        self,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
        journal_id: int,
        cause: _Cause,
        campaign_id: int | None,
        known_stream_ids: set[int],
    ) -> CampaignCreationFailedError:
        archived_something, leftovers = self._archive_created(campaign_id, known_stream_ids)
        if leftovers:
            return self._fail_with_leftovers(entry, journal, journal_id, cause, leftovers)
        message = f"Кампания не создана: {cause.message}"
        if archived_something:
            message += ". Созданное в Keitaro перенесено в архив"
        return self._finish_with_error(
            entry, journal, journal_id, CreationStatus.FAILED, message, cause
        )

    def _archive_created(
        self, campaign_id: int | None, known_stream_ids: set[int]
    ) -> tuple[bool, list[str]]:
        """Archives streams first and the campaign last: archiving a campaign leaves its streams."""
        if campaign_id is None:
            return False, []
        stream_ids = set(known_stream_ids)
        streams_listed = True
        try:
            # Catches a stream whose creation response was lost.
            for stream in self._client.get_campaign_streams(campaign_id):
                stream_ids.add(stream.id)
        except Exception:
            streams_listed = False

        archived_something = False
        failed_stream_ids: list[int] = []
        for stream_id in sorted(stream_ids):
            try:
                self._client.archive_stream(stream_id)
                archived_something = True
            except Exception:
                failed_stream_ids.append(stream_id)

        leftovers: list[str] = []
        try:
            self._client.archive_campaign(campaign_id)
            archived_something = True
        except Exception:
            leftovers.append(f"кампания {campaign_id}")
        if failed_stream_ids:
            leftovers.append(
                "потоки " + ", ".join(str(stream_id) for stream_id in failed_stream_ids)
            )
        if not streams_listed:
            leftovers.append("список потоков не прочитан")
        return archived_something, leftovers

    def _fail_with_leftovers(
        self,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
        journal_id: int,
        cause: _Cause,
        leftovers: list[str],
    ) -> CampaignCreationFailedError:
        message = (
            f"Кампания не создана: {cause.message}. "
            f"Не удалось убрать в архив: {'; '.join(leftovers)} "
            f"— нужна ручная уборка (журнал #{journal_id})"
        )
        failure = _Cause(message, COMPENSATION_FAILED_CODE, COMPENSATION_FAILED_HTTP_STATUS)
        return self._finish_with_error(
            entry, journal, journal_id, CreationStatus.COMPENSATION_FAILED, message, failure
        )

    def _finish_with_error(
        self,
        entry: CreatedCampaign,
        journal: CreatedCampaignsRepository,
        journal_id: int,
        status: CreationStatus,
        message: str,
        cause: _Cause,
    ) -> CampaignCreationFailedError:
        entry.status = status
        entry.error = message
        try:
            journal.save(entry)
        except Exception:
            # The user still gets the compensation result; the log keeps the failed write.
            logger.exception("Could not write the final state of journal entry %s", journal_id)
            message += f" (журнал #{journal_id} не обновлён)"
        return CampaignCreationFailedError(message, cause.code, cause.http_status)
