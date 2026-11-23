import pytest

from app.services.campaign_catalog import CampaignCatalog
from tests.fakes import FakeKeitaroClient

TTL_SECONDS = 30.0


class ManualClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fake() -> FakeKeitaroClient:
    client = FakeKeitaroClient()
    client.add_campaign("test_oso4lq_a")
    client.add_campaign("other")
    client.add_campaign("test_oso4lq_b")
    return client


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def catalog(fake, clock) -> CampaignCatalog:
    return CampaignCatalog(fake, ttl_seconds=TTL_SECONDS, clock=clock)


def ids(campaigns) -> list[int]:
    return [campaign.id for campaign in campaigns]


def test_search_lists_newest_first_and_matches_id_or_name(catalog):
    assert ids(catalog.search("")) == [3, 2, 1]
    assert ids(catalog.search("oso4lq")) == [3, 1]
    assert ids(catalog.search("2")) == [2]


def test_campaign_list_is_cached_for_ttl(fake, catalog, clock):
    catalog.search("")
    assert fake.calls.count(("list_campaigns",)) == 1
    clock.now += 29
    catalog.search("")
    assert fake.calls.count(("list_campaigns",)) == 1
    clock.now += 2
    catalog.search("")
    assert fake.calls.count(("list_campaigns",)) == 2
