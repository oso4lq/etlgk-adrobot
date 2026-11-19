import pytest

from app.keitaro.errors import KeitaroNotFoundError, KeitaroUnavailableError
from app.keitaro.models import (
    NewCampaign,
    NewCountryRedirectStream,
    NewOffersStream,
    StreamOfferShare,
)
from tests.fakes import FakeKeitaroClient

NEW_CAMPAIGN = NewCampaign("c", "alias1", 1813, 10332, 836)


def make_campaign_with_streams(fake: FakeKeitaroClient):
    campaign = fake.create_campaign(NEW_CAMPAIGN)
    redirect = fake.create_country_redirect_stream(
        NewCountryRedirectStream(campaign.id, "geo", 1, "DE", "https://google.com")
    )
    offers = fake.create_offers_stream(
        NewOffersStream(campaign.id, "rest", 2, (StreamOfferShare(18813, 100),))
    )
    return campaign, redirect, offers


def test_created_objects_look_like_keitaro_and_ids_grow():
    fake = FakeKeitaroClient()
    campaign, redirect, offers = make_campaign_with_streams(fake)
    assert campaign.domain == "https://kylovoa.com/"
    assert (redirect.flow_schema, redirect.action_type, redirect.offers) == ("redirect", "http", [])
    assert (offers.flow_schema, offers.position, offers.offers[0].state) == (
        "landings",
        2,
        "active",
    )
    assert redirect.id < offers.id
    assert [call[0] for call in fake.calls] == [
        "create_campaign",
        "create_country_redirect_stream",
        "create_offers_stream",
    ]


def test_campaign_without_domain():
    fake = FakeKeitaroClient()
    fake.campaign_domain = None
    assert fake.create_campaign(NEW_CAMPAIGN).domain is None


def test_archived_objects_are_hidden_like_in_keitaro():
    fake = FakeKeitaroClient()
    campaign, redirect, offers = make_campaign_with_streams(fake)
    fake.archive_stream(redirect.id)
    assert [s.id for s in fake.get_campaign_streams(campaign.id)] == [offers.id]
    assert fake.get_stream(redirect.id).state == "deleted"
    fake.archive_campaign(campaign.id)
    assert fake.list_campaigns() == []
    with pytest.raises(KeitaroNotFoundError):
        fake.get_campaign(campaign.id)


def test_unknown_ids_raise_not_found():
    fake = FakeKeitaroClient()
    for call in (fake.get_campaign, fake.get_stream, fake.archive_stream, fake.archive_campaign):
        with pytest.raises(KeitaroNotFoundError):
            call(999)


def test_replace_stream_offers_replaces_the_list():
    fake = FakeKeitaroClient()
    _, _, offers = make_campaign_with_streams(fake)
    fake.replace_stream_offers(offers.id, [StreamOfferShare(1, 40), StreamOfferShare(2, 60)])
    assert [(o.offer_id, o.share) for o in fake.get_stream(offers.id).offers] == [(1, 40), (2, 60)]


def test_fail_raises_given_number_of_times_without_applying():
    fake = FakeKeitaroClient()
    fake.fail("create_campaign", KeitaroUnavailableError("down"), times=2)
    for _ in range(2):
        with pytest.raises(KeitaroUnavailableError):
            fake.create_campaign(NEW_CAMPAIGN)
    assert fake.campaigns == {}
    assert fake.create_campaign(NEW_CAMPAIGN).id == 1


def test_fail_after_applying_leaves_the_object_created():
    fake = FakeKeitaroClient()
    fake.fail("create_campaign", KeitaroUnavailableError("timeout"), after_applying=True)
    with pytest.raises(KeitaroUnavailableError):
        fake.create_campaign(NEW_CAMPAIGN)
    assert list(fake.campaigns) == [1]
