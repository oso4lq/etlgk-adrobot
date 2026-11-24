import pytest
from sqlalchemy.orm import Session

from app.db.models import CreationStatus
from app.keitaro.errors import KeitaroAliasTakenError, KeitaroUnavailableError
from app.keitaro.models import StreamOfferShare
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.services.campaign_creator import (
    CampaignCreator,
    CampaignRequest,
    InvalidCampaignNameError,
    NamePrefixRequiredError,
    UnknownCountryError,
)
from app.services.creator_references import CreatorMisconfiguredError, CreatorReferenceResolver
from app.services.offer_catalog import OfferCatalog, OfferNotFoundError


def writes_of(fake):
    return [call for call in fake.calls if call[0].startswith(("create", "archive"))]


def test_creates_campaign_with_country_stream_first(creator, fake, journal):
    entry = creator.create(journal, CampaignRequest("test_oso4lq_one", "DE", 18813))

    writes = writes_of(fake)
    assert [call[0] for call in writes] == [
        "create_campaign",
        "create_country_redirect_stream",
        "create_offers_stream",
    ]
    country_stream, offers_stream = writes[1][1], writes[2][1]
    assert (
        country_stream.position,
        country_stream.country_code,
        country_stream.redirect_url,
    ) == (1, "DE", "https://google.com")
    assert (offers_stream.position, offers_stream.offers) == (2, (StreamOfferShare(18813, 100),))
    assert (country_stream.name, offers_stream.name) == ("Flow 1", "Flow 2")
    assert entry.status == CreationStatus.CREATED and entry.alias == "alias1"
    assert entry.campaign_url == "https://kylovoa.com/alias1"
    assert entry.country_stream_id and entry.offers_stream_id and entry.keitaro_campaign_id
    assert journal.list_recent() == [entry]


def test_alias_taken_retries_with_new_alias(creator, fake, journal):
    fake.fail("create_campaign", KeitaroAliasTakenError("taken", 422, frozenset({"alias"})))

    entry = creator.create(journal, CampaignRequest("test_oso4lq_one", "DE", 18813))

    assert entry.alias == "alias2"
    assert [c for c in fake.calls if c[0] == "create_campaign"] == [
        ("create_campaign", "alias1"),
        ("create_campaign", "alias2"),
    ]


@pytest.mark.parametrize(
    ("request_", "error_class"),
    [
        (CampaignRequest("   ", "DE", 18813), InvalidCampaignNameError),
        (CampaignRequest("other_campaign", "DE", 18813), NamePrefixRequiredError),
        (CampaignRequest("test_oso4lq_x", "XX", 18813), UnknownCountryError),
        (CampaignRequest("test_oso4lq_x", "DE", 99999), OfferNotFoundError),
    ],
)
def test_invalid_input_is_rejected_before_any_write(creator, fake, journal, request_, error_class):
    with pytest.raises(error_class):
        creator.create(journal, request_)

    assert not writes_of(fake)
    assert journal.list_recent() == []


@pytest.mark.parametrize(
    ("request_", "code", "message"),
    [
        (
            CampaignRequest(" ", "DE", 18813),
            "invalid_name",
            "Название кампании не может быть пустым",
        ),
        (
            CampaignRequest("other", "DE", 18813),
            "name_prefix_required",
            "Название кампании должно начинаться с «test_oso4lq_»",
        ),
        (
            CampaignRequest("test_oso4lq_x", " xx ", 18813),
            "unknown_country",
            "Неизвестный код страны: xx",
        ),
        (
            CampaignRequest("test_oso4lq_x", "DE", 99999),
            "offer_not_found",
            "Оффер 99999 не найден в Keitaro",
        ),
    ],
)
def test_rejections_carry_code_status_and_russian_message(
    creator, journal, request_, code, message
):
    with pytest.raises(Exception) as error:
        creator.create(journal, request_)

    assert (error.value.code, error.value.http_status, error.value.message) == (code, 422, message)


def test_empty_prefix_allows_any_name(fake, journal, make_settings):
    settings = make_settings(
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
    )
    creator = CampaignCreator(
        fake,
        OfferCatalog(fake, ttl_seconds=300),
        CreatorReferenceResolver(fake, settings),
        settings,
        generate_alias=lambda: "abc123",
    )

    entry = creator.create(journal, CampaignRequest("any name", "DE", 18813))

    assert entry.status == CreationStatus.CREATED


def test_misconfigured_references_are_rejected_before_any_write(fake, journal, creator_settings):
    settings = creator_settings.model_copy(update={"campaign_domain": "kylovoa.org"})
    creator = CampaignCreator(
        fake,
        OfferCatalog(fake, ttl_seconds=300),
        CreatorReferenceResolver(fake, settings),
        settings,
    )

    with pytest.raises(CreatorMisconfiguredError):
        creator.create(journal, CampaignRequest("test_oso4lq_x", "DE", 18813))

    assert not writes_of(fake)
    assert journal.list_recent() == []


def test_name_is_trimmed_before_prefix_check(creator, fake, journal):
    entry = creator.create(journal, CampaignRequest("  test_oso4lq_x  ", "DE", 18813))

    assert entry.name == "test_oso4lq_x"
    assert next(iter(fake.campaigns.values())).name == "test_oso4lq_x"


def test_country_code_is_normalized(creator, fake, journal):
    entry = creator.create(journal, CampaignRequest("test_oso4lq_x", "de", 18813))

    country_stream = writes_of(fake)[1][1]
    assert country_stream.country_code == "DE" and entry.country == "DE"


def test_keitaro_down_during_validation_writes_nothing(creator, fake, journal):
    fake.fail("list_offers", KeitaroUnavailableError("Keitaro недоступен: таймаут"))

    with pytest.raises(KeitaroUnavailableError):
        creator.create(journal, CampaignRequest("test_oso4lq_x", "DE", 18813))

    assert not writes_of(fake)
    assert journal.list_recent() == []


def test_campaign_url_falls_back_to_configured_domain(creator, fake, journal):
    fake.campaign_domain = None

    entry = creator.create(journal, CampaignRequest("test_oso4lq_x", "DE", 18813))

    assert entry.campaign_url == "https://kylovoa.com/alias1"


def test_journal_entry_is_pending_before_first_write(creator, fake, journal, db_session):
    seen = []
    original = fake.create_campaign

    def spying_create_campaign(campaign):
        # A second session sees only committed rows.
        with Session(db_session.get_bind()) as other_session:
            seen.append(
                [row.status for row in CreatedCampaignsRepository(other_session).list_recent()]
            )
        return original(campaign)

    fake.create_campaign = spying_create_campaign

    creator.create(journal, CampaignRequest("test_oso4lq_x", "DE", 18813))

    assert seen == [[CreationStatus.PENDING]]
